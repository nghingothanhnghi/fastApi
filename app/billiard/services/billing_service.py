# app/billiard/services/billing_service.py
# Chooses the pricing rule for a session and computes the table fee from the
# SESSION'S OWN SNAPSHOT. Read-only: never writes, never commits.
# Imports no lifecycle module, so session_lifecycle can use it without a cycle.
#
# DESIGN DECISIONS
#   * The rule is chosen ONCE, at session start (by the start time, club-local).
#     The rate then stays fixed for the whole session. A session that runs past
#     the end of a happy-hour window keeps the happy-hour rate. Splitting a bill
#     across rate windows is a possible later enhancement.
#   * Everything needed to bill is copied into the session (hourly_rate,
#     billing_policy, pricing_snapshot). Editing or deleting a rule later never
#     changes an existing session or bill.
#   * Which rule wins when several match: highest priority, then a table-specific
#     rule over a tenant-wide one, then the newest rule.
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.billiard import config
from app.billiard.models import BilliardTable, PricingRule
from app.billiard.utils.billing import as_utc, calculate_fee

_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@dataclass(frozen=True)
class PriceQuote:
    hourly_rate: Decimal
    rule_type: str
    params: dict = field(default_factory=dict)
    rule_id: Optional[int] = None
    rule_name: Optional[str] = None

    def snapshot(self, at: datetime) -> dict:
        """JSON stored in TableSession.pricing_snapshot (strings only)."""
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "rule_type": self.rule_type,
            "hourly_rate": str(self.hourly_rate),
            "params": dict(self.params),
            "priced_at": as_utc(at).isoformat(),
        }


def _to_local(at: datetime) -> datetime:
    """Naive input = already club-local time (same convention as the reports)."""
    if at.tzinfo is None:
        return at.replace(tzinfo=config.LOCAL_TZ)
    return at.astimezone(config.LOCAL_TZ)


def _matches(rule: PricingRule, local: datetime) -> bool:
    start, end = rule.start_time, rule.end_time
    now_t = local.time()
    weekday = local.weekday()

    if start is not None and end is not None:
        if start <= end:
            if not (start <= now_t <= end):
                return False
        else:   # overnight window, e.g. 22:00 -> 02:00
            if not (now_t >= start or now_t <= end):
                return False
            if now_t <= end:
                weekday = (weekday - 1) % 7   # after midnight: belongs to the previous day's window

    if rule.days_of_week:
        days = {d.strip().lower() for d in rule.days_of_week.split(",") if d.strip()}
        if _DAYS[weekday] not in days:
            return False
    return True


class BillingService:

    @staticmethod
    def select_rule(db: Session, table: BilliardTable, at: datetime) -> Optional[PricingRule]:
        rules = db.execute(
            select(PricingRule).where(
                PricingRule.client_id == table.client_id,
                PricingRule.is_active.is_(True),
                or_(PricingRule.table_id.is_(None), PricingRule.table_id == table.id),
            )
        ).scalars().all()
        local = _to_local(at)
        matching = [r for r in rules if _matches(r, local)]
        return max(
            matching,
            key=lambda r: (r.priority, 1 if r.table_id is not None else 0, r.id),
            default=None,
        )

    @staticmethod
    def quote_for_table(db: Session, table: BilliardTable, at: datetime) -> PriceQuote:
        rule = BillingService.select_rule(db, table, at)
        if rule is None:   # no rule: table's own rate + the configured default policy
            return PriceQuote(
                hourly_rate=Decimal(str(table.hourly_rate)),
                rule_type=config.BILLING_POLICY.value,
            )
        rate = rule.hourly_rate if rule.hourly_rate is not None else table.hourly_rate
        return PriceQuote(
            hourly_rate=Decimal(str(rate)),
            rule_type=rule.rule_type.value,
            params=dict(rule.params or {}),
            rule_id=rule.id,
            rule_name=rule.name,
        )

    @staticmethod
    def table_fee(session, minutes: int) -> Decimal:
        """Fee from the session's own snapshot. Sessions created before pricing
        rules existed have no snapshot and fall back to billing_policy
        ('per_minute' / 'rounded_hour'), giving exactly the old result."""
        snap = getattr(session, "pricing_snapshot", None) or {}
        return calculate_fee(
            snap.get("rule_type") or session.billing_policy,
            session.hourly_rate,
            minutes,
            snap.get("params"),
        )

    @staticmethod
    def preview_fee(db: Session, table: BilliardTable, at: datetime, minutes: int) -> dict:
        """What a session starting at `at` and lasting `minutes` would cost."""
        quote = BillingService.quote_for_table(db, table, at)
        fee = calculate_fee(quote.rule_type, quote.hourly_rate, minutes, quote.params)
        return {
            "table_id": table.id,
            "at": _to_local(at),
            "minutes": minutes,
            "rule_id": quote.rule_id,
            "rule_name": quote.rule_name,
            "rule_type": quote.rule_type,
            "hourly_rate": quote.hourly_rate,
            "params": quote.params,
            "fee": fee,
        }


billing_service = BillingService()