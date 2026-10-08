# app/billiard/utils/billing.py
# Pure functions, no database. Replaces the previous version; every old name is kept.
import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from app.billiard import config
from app.billiard.config import BillingPolicy

CENT = Decimal("0.01")

DEFAULT_BLOCK_MINUTES = 60
DEFAULT_MIN_MINUTES = 60

# Legacy policy names stored on old sessions map onto the new rule types.
_ALIASES = {"rounded_hour": "hourly"}


def as_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes even for DateTime(timezone=True)."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def billable_minutes(start: datetime, end: datetime) -> int:
    seconds = max((as_utc(end) - as_utc(start)).total_seconds(), 0)
    return max(config.MIN_BILLABLE_MINUTES, math.ceil(seconds / 60))


def _round_fee(fee: Decimal) -> Decimal:
    unit = config.FEE_ROUNDING_UNIT
    if unit > 0:
        fee = (fee / unit).to_integral_value(rounding=ROUND_HALF_UP) * unit
    return fee.quantize(CENT, rounding=ROUND_HALF_UP)


def _positive_int(value, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if n > 0 else default


def calculate_fee(rule_type: str, hourly_rate, minutes: int, params: Optional[dict] = None) -> Decimal:
    """
    per_minute    prorated:                     rate x minutes / 60
    hourly        every started hour is full:   rate x ceil(minutes / 60)   (legacy 'rounded_hour')
    block         every started block is full:  rate x block_minutes/60 x ceil(minutes / block_minutes)
                  params: block_minutes (default 60)
    minimum_hour  prorated, with a floor:       rate x max(minutes, min_minutes) / 60
                  params: min_minutes (default 60)
    """
    kind = _ALIASES.get(rule_type, rule_type)
    rate = Decimal(str(hourly_rate))
    mins = int(minutes)
    params = params or {}

    if kind == "per_minute":
        fee = rate * Decimal(mins) / Decimal(60)
    elif kind == "hourly":
        fee = rate * Decimal((mins + 59) // 60)
    elif kind == "block":
        size = _positive_int(params.get("block_minutes"), DEFAULT_BLOCK_MINUTES)
        blocks = -(-mins // size)
        fee = rate * Decimal(size) / Decimal(60) * Decimal(blocks)
    elif kind == "minimum_hour":
        floor = _positive_int(params.get("min_minutes"), DEFAULT_MIN_MINUTES)
        fee = rate * Decimal(max(mins, floor)) / Decimal(60)
    else:
        raise ValueError(f"Unknown pricing rule type '{rule_type}'")
    return _round_fee(fee)


def calculate_table_fee(hourly_rate: Decimal, minutes: int, policy: BillingPolicy) -> Decimal:
    """Kept for existing callers; new code should use billing_service.table_fee."""
    return calculate_fee(policy.value, hourly_rate, minutes)