# app/billiard/services/session_lifecycle.py
# The ONLY place that creates a TableSession (with its rate/policy snapshot) or
# finalizes one (fee, totals, table freed). Used by the POS path
# (table_service.start_session / session_service.stop_session) AND the device
# path (event_service), so billing can never differ between the two.
# No imports from other services (same rule as table_lifecycle / game_lifecycle),
# except billing_service, which is read-only and imports no lifecycle module.
# Never commits or locks; the caller holds the row locks.
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.billiard.models import BilliardPackage, BilliardTable, SessionItem, SessionStatus, TableSession
from app.billiard.models.session import (
    BILLING_REVIEW_REQUIRED, BILLING_REVIEW_RESOLVED, REVIEW_ASSIGN_PACKAGE, REVIEW_CONFIRM_NORMAL,
)
from app.billiard.services.billing_service import billing_service, snapshot_package
from app.billiard.services.game_lifecycle import cancel_active_game, close_active_game
from app.billiard.services.table_lifecycle import mark_available, mark_playing
from app.billiard.utils.billing import CENT, as_utc, billable_minutes


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


def discount_spec(session: TableSession) -> Optional[dict]:
    """The intended discount, {"type": "percent" | "fixed", "value": "10"}, or None.
    Kept in the pricing snapshot so a percent follows the table fee that is final only at Stop."""
    spec = (session.pricing_snapshot or {}).get("discount")
    return spec if isinstance(spec, dict) and spec.get("type") in ("percent", "fixed") else None


def discount_amount(session: TableSession, subtotal: Decimal) -> Decimal:
    """Amount taken off `subtotal` (table fee + products), never below 0 or above the subtotal.
    percent: value % of the subtotal. fixed: the value. No spec: the stored `discount`
    column as a fixed amount (sessions discounted before specs existed)."""
    spec = discount_spec(session)
    if spec and spec["type"] == "percent":
        amount = (subtotal * Decimal(str(spec["value"])) / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
    elif spec:
        amount = Decimal(str(spec["value"]))
    else:
        amount = session.discount or Decimal("0")
    return max(min(amount, subtotal), Decimal("0"))


def recompute_totals(session: TableSession) -> None:
    """The ONE place that derives product fee, discount and grand total from the session's
    own parts: grand_total = max(table_fee + product_fee - discount, 0).
    Call it after anything that changes the table fee, the items or the discount.
    With no discount the result is exactly table_fee + product_fee (old behaviour)."""
    session.total_product_fee = sum((i.total_price for i in session.items), Decimal("0"))
    subtotal = session.total_table_fee + session.total_product_fee
    session.discount = discount_amount(session, subtotal)
    session.grand_total = max(subtotal - session.discount, Decimal("0"))


def apply_discount(
    session: TableSession, *, amount: Optional[Decimal] = None, percent: Optional[Decimal] = None,
    reason: Optional[str] = None, by_id: Optional[int] = None,
) -> None:
    """Set (or, with amount == 0, remove) the discount and recompute. Exactly one of
    amount / percent. The caller has checked the session state, the role and that no
    payment order exists. The spec is stored; session.discount becomes the applied amount."""
    if (amount is None) == (percent is None):
        raise ValueError("Give either amount or percent")
    snap = dict(session.pricing_snapshot or {})        # new dict so the JSON change is saved
    if percent is not None:
        if not (Decimal("0") < percent <= Decimal("100")):
            raise ValueError("percent must be greater than 0 and at most 100")
        snap["discount"] = {"type": "percent", "value": str(percent)}
    elif amount < 0:
        raise ValueError("amount cannot be negative")
    elif amount == 0:
        snap.pop("discount", None)
        session.discount = Decimal("0")
    else:
        snap["discount"] = {"type": "fixed", "value": str(amount)}
    session.pricing_snapshot = snap
    session.discount_reason = reason if (percent is not None or amount) else None
    session.discounted_by_id = by_id
    recompute_totals(session)


MAX_PLANNED_MINUTES = 1440      # 24 h


def _check_minutes(minutes: int) -> None:
    if not isinstance(minutes, int) or not (1 <= minutes <= MAX_PLANNED_MINUTES):
        raise ValueError(f"minutes must be between 1 and {MAX_PLANNED_MINUTES}")


def _set_package(session: TableSession, package: BilliardPackage) -> None:
    """Freeze the package into the session (the ONE place package terms are written)."""
    snap = snapshot_package(package)
    session.package_id = package.id            # id/name/price columns: for reports; billing reads the snapshot
    session.package_name = package.name
    session.package_price = Decimal(snap["price"])
    session.package_snapshot = snap


def open_session(
    db: Session, table: BilliardTable, opened_by_id: Optional[int], at: Optional[datetime] = None,
    planned_minutes: Optional[int] = None, package: Optional[BilliardPackage] = None,
) -> TableSession:
    """Start a session on a locked table. Raises ValueError if the table can't start one.
    May raise IntegrityError from the flush (uq_one_active_session_per_table).

    planned_minutes sets ends_at = start + planned_minutes (timed play). It is a countdown
    and an overtime flag only: the bill is still computed from the real start and stop.

    package (already loaded by the caller, who checked the club): its terms are frozen into the
    session and ends_at = start + its duration. Use planned_minutes OR package, not both."""
    if planned_minutes is not None:
        _check_minutes(planned_minutes)
    if package is not None:
        if planned_minutes is not None:
            raise ValueError("Choose a package or planned_minutes, not both")
        if not package.is_active:
            raise ValueError("Package is not available")
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
        ends_at=start + timedelta(minutes=planned_minutes) if planned_minutes else None,
    )
    if package is not None:
        _set_package(session, package)
        session.ends_at = start + timedelta(minutes=package.duration_minutes)

    db.add(session)
    db.flush()
    return session


def extend_session(session: TableSession, minutes: int, now: Optional[datetime] = None) -> TableSession:
    """Move ends_at forward by `minutes` (ACTIVE sessions only). The base is the current
    ends_at, or the present moment when there is none or it has already passed, so an
    extension always gives the customer the full `minutes` from now. Billing is unchanged."""
    if session.status != SessionStatus.ACTIVE:
        raise ValueError("Only an active session can be extended")
    _check_minutes(minutes)
    now = as_utc(now) if now else datetime.now(timezone.utc)
    current = as_utc(session.ends_at) if session.ends_at else None
    base = current if current and current > now else now
    session.ends_at = base + timedelta(minutes=minutes)
    return session


def flag_billing_review(session: TableSession, requested_package_id, reason: str) -> None:
    """A device asked for a package that could not be applied. Records what was asked and why it failed;
    payment stays blocked (payment_adapter) until resolve_billing_review. Never touches package terms or fees."""
    session.billing_review_state = BILLING_REVIEW_REQUIRED
    session.requested_package_id = requested_package_id if isinstance(requested_package_id, int) and not isinstance(requested_package_id, bool) else None
    session.billing_review_reason = reason[:255]


def _give_included_items(session: TableSession) -> None:
    """Turn units already added at full price into the package's free units (first come, first free),
    up to each product's included_quantity. Used when a package is assigned after items were added."""
    for entry in (session.package_snapshot or {}).get("items", []):
        pid = entry["product_id"]
        left = entry["included_quantity"] - sum(i.quantity for i in session.items if i.from_package and i.product_id == pid)
        for item in [i for i in session.items if i.product_id == pid and not i.from_package]:
            if left <= 0:
                break
            take = min(item.quantity, left)
            left -= take
            if take < item.quantity:                       # split: the free part becomes its own line
                item.quantity -= take
                item.total_price = item.unit_price * item.quantity
                session.items.append(SessionItem(
                    product_id=item.product_id, variant_id=item.variant_id, product_name=f"{item.product_name} (package)",
                    quantity=take, unit_price=Decimal("0.00"), total_price=Decimal("0.00"),
                    from_package=True, added_by_id=item.added_by_id,
                ))
            else:                                          # the whole line is free
                item.product_name = f"{item.product_name} (package)"
                item.unit_price = Decimal("0.00")
                item.total_price = Decimal("0.00")
                item.from_package = True


def _bill_view(session: TableSession) -> dict:
    """What the customer owes right now, as strings, for the audit record."""
    package = session.package_snapshot or None
    return {
        "total_table_fee": str(session.total_table_fee), "total_product_fee": str(session.total_product_fee),
        "discount": str(session.discount), "grand_total": str(session.grand_total),
        "free_units": sum(i.quantity for i in session.items if i.from_package),
        "package": {k: package[k] for k in ("package_id", "name", "price", "duration_minutes")} if package else None,
    }


def resolve_billing_review(
    session: TableSession, *, action: str, by_id: Optional[int], note: Optional[str],
    package: Optional[BilliardPackage] = None, at: Optional[datetime] = None,
    resolver_roles: Optional[list[str]] = None,
) -> TableSession:
    """Close a billing review, once. The caller checked the role, the club, that the package is active and
    that no payment was started. Who, when, what and the note stay on the session (the audit record).

    assign_package          snapshot the package now (price, duration, free products incl. items already added);
                            a stopped session gets its table fee recomputed, an active one at Stop.
    confirm_normal_pricing  keep normal per-rule pricing on purpose (note required)."""
    if session.billing_review_state != BILLING_REVIEW_REQUIRED:
        raise ValueError("This session has no billing review to resolve")
    if session.status == SessionStatus.CANCELLED:
        raise ValueError("Session was cancelled")
    before = _bill_view(session)
    if action == REVIEW_ASSIGN_PACKAGE:
        if package is None:
            raise ValueError("A package is required")
        if not package.is_active:
            raise ValueError("Package is not available")
        _set_package(session, package)
        if session.ends_at is None and session.status == SessionStatus.ACTIVE:
            session.ends_at = as_utc(session.start_time) + timedelta(minutes=package.duration_minutes)
        _give_included_items(session)
        if session.status == SessionStatus.COMPLETED:      # the fee was already computed without the package
            session.total_table_fee = billing_service.table_fee(session, session.duration_minutes)
        recompute_totals(session)
    elif action == REVIEW_CONFIRM_NORMAL:
        pass
    else:
        raise ValueError("Unknown billing review action")
    session.billing_review_state = BILLING_REVIEW_RESOLVED
    session.billing_review_resolution = action
    session.billing_review_note = note
    session.billing_reviewed_by_id = by_id
    session.billing_reviewed_at = at or datetime.now(timezone.utc)
    session.billing_review_audit = {            # new dict: the JSON change is saved. requested_package_id / reason stay untouched
        "action": action, "resolver_roles": sorted(resolver_roles or []),
        "requested_package_id": session.requested_package_id, "reason": session.billing_review_reason,
        "before": before, "after": _bill_view(session),
    }
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
