# app/billiard/utils/billing.py
import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from app.billiard import config
from app.billiard.config import BillingPolicy

CENT = Decimal("0.01")


def as_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes even for DateTime(timezone=True)."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def billable_minutes(start: datetime, end: datetime) -> int:
    seconds = max((as_utc(end) - as_utc(start)).total_seconds(), 0)
    return max(config.MIN_BILLABLE_MINUTES, math.ceil(seconds / 60))


def calculate_table_fee(hourly_rate: Decimal, minutes: int, policy: BillingPolicy) -> Decimal:
    if policy == BillingPolicy.ROUNDED_HOUR:
        hours = Decimal((minutes + 59) // 60)
    else:
        hours = Decimal(minutes) / Decimal(60)

    fee = Decimal(hourly_rate) * hours
    unit = config.FEE_ROUNDING_UNIT
    if unit > 0:
        fee = (fee / unit).to_integral_value(rounding=ROUND_HALF_UP) * unit
    return fee.quantize(CENT, rounding=ROUND_HALF_UP)