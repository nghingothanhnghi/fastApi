# app/billiard/services/session_lifecycle.py
# The ONLY place that creates a TableSession (with its rate/policy snapshot) or
# finalizes one (fee, totals, table freed). Used by the POS path
# (table_service.start_session / session_service.stop_session) AND the device
# path (event_service), so billing can never differ between the two.
# No imports from other services (same rule as table_lifecycle / game_lifecycle),
# except billing_service, which is read-only and imports no lifecycle module.
# Never commits or locks; the caller holds the row locks.
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.billiard.models import BilliardTable, SessionStatus, TableSession
from app.billiard.services.billing_service import billing_service
from app.billiard.services.game_lifecycle import cancel_active_game, close_active_game
from app.billiard.services.table_lifecycle import mark_available, mark_playing
from app.billiard.utils.billing import as_utc, billable_minutes


def resolve_time(at: Optional[datetime], floor: Optional[datetime] = None) -> tuple[datetime, str]:
    """(utc_time, source). `at` is a device timestamp (clock already vetted by the
    caller). It is never allowed to be in the future, nor earlier than `floor`,
    so a skewed ESP32 clock cannot invent billable time."""
    now = datetime.now(timezone.utc)
    if at is None:
        value, source = now, "server"
    else:
        value, source = min(as_utc(at), now), "device"
    if floor is not None and value < as_utc(floor):
        value = as_utc(floor)
    return value, source


def recompute_totals(session: TableSession) -> None:
    """The ONE place that derives product fee and grand total from the session's
    own parts: grand_total = max(table_fee + product_fee - discount, 0).
    Call it after anything that changes the table fee, the items or the discount.
    With discount = 0 the result is exactly table_fee + product_fee (old behaviour)."""
    session.total_product_fee = sum((i.total_price for i in session.items), Decimal("0"))
    discount = session.discount or Decimal("0")
    session.grand_total = max(session.total_table_fee + session.total_product_fee - discount, Decimal("0"))


def open_session(
    db: Session, table: BilliardTable, opened_by_id: Optional[int], at: Optional[datetime] = None
) -> TableSession:
    """Start a session on a locked table. Raises ValueError if the table can't start one.
    May raise IntegrityError from the flush (uq_one_active_session_per_table)."""
    mark_playing(table)
    start, source = resolve_time(at)
    # The rule is chosen once, by the start time, and frozen into the session
    # (rate + rule type + params). With no matching rule this is exactly the old
    # behaviour: table rate + configured default policy.
    quote = billing_service.quote_for_table(db, table, start)
    session = TableSession(
        table_id=table.id,
        start_time=start,
        start_time_source=source,
        status=SessionStatus.ACTIVE,
        hourly_rate=quote.hourly_rate,                 # snapshot
        billing_policy=quote.rule_type,                # snapshot
        pricing_snapshot=quote.snapshot(start),        # snapshot (rule id/name/params)
        opened_by_id=opened_by_id,
    )
    db.add(session)
    db.flush()
    return session


def finalize_stop(
    db: Session, session: TableSession, table: BilliardTable,
    stopped_by_id: Optional[int], at: Optional[datetime] = None,
) -> TableSession:
    """Complete an ACTIVE session: official duration + fee, close its running
    game, free the table. Caller must have checked status == ACTIVE."""
    end, source = resolve_time(at, floor=session.start_time)
    minutes = billable_minutes(session.start_time, end)
    fee = billing_service.table_fee(session, minutes)   # from the session's own snapshot

    session.end_time = end
    session.end_time_source = source
    session.status = SessionStatus.COMPLETED
    session.duration_minutes = minutes
    session.total_table_fee = fee
    recompute_totals(session)
    session.stopped_by_id = stopped_by_id

    close_active_game(db, session, end)    # a stopped session must not leave a game running
    mark_available(table)                  # bill is generated at STOP, not at payment
    db.flush()
    return session


def cancel_session(
    db: Session, session: TableSession, table: BilliardTable,
    cancelled_by_id: Optional[int], reason: str, at: Optional[datetime] = None,
) -> TableSession:
    """Cancel an ACTIVE session (opened by mistake): no bill, no payment. Keeps the rows
    (items, games, who/why/when) for audit, zeroes every total, ends the running game as
    CANCELLED and frees the table. Caller must have checked status == ACTIVE and the role."""
    end, source = resolve_time(at, floor=session.start_time)

    session.status = SessionStatus.CANCELLED
    session.end_time = end
    session.end_time_source = source
    session.cancelled_at = end
    session.cancelled_by_id = cancelled_by_id
    session.cancel_reason = reason
    session.total_table_fee = Decimal("0")
    session.total_product_fee = Decimal("0")
    session.grand_total = Decimal("0")      # nothing to charge; not via recompute_totals (items are kept)

    cancel_active_game(db, session, end)
    mark_available(table)
    db.flush()
    return session
