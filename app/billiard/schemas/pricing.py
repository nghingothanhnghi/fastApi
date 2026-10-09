# app/billiard/schemas/pricing.py
from datetime import datetime, time
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.billiard.models.pricing_rule import PricingRuleType

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def normalize_days(value: Optional[str]) -> Optional[str]:
    """'Sat, SUN' -> 'sat,sun'. Empty -> None (= every day)."""
    if value is None:
        return None
    parts = [p.strip().lower() for p in str(value).split(",") if p.strip()]
    if not parts:
        return None
    bad = [p for p in parts if p not in DAYS]
    if bad:
        raise ValueError(f"Invalid day(s): {', '.join(bad)}. Use mon,tue,wed,thu,fri,sat,sun")
    ordered = [d for d in DAYS if d in parts]   # dedupe, week order
    return ",".join(ordered)


def normalize_params(rule_type, params: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Keep only the knobs the rule type understands, with defaults and bounds."""
    rule_type = PricingRuleType(rule_type)
    params = dict(params or {})

    def _minutes(key: str) -> int:
        raw = params.get(key, 60)
        try:
            n = int(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be an integer number of minutes")
        if not 1 <= n <= 1440:
            raise ValueError(f"{key} must be between 1 and 1440")
        return n

    if rule_type == PricingRuleType.BLOCK:
        return {"block_minutes": _minutes("block_minutes")}
    if rule_type == PricingRuleType.MINIMUM_HOUR:
        return {"min_minutes": _minutes("min_minutes")}
    return {}


class PricingRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    rule_type: PricingRuleType
    hourly_rate: Optional[Decimal] = Field(None, gt=0, max_digits=12, decimal_places=2,
                                           description="Overrides the table's own rate when set")
    params: Optional[dict[str, Any]] = None
    table_id: Optional[int] = Field(None, description="Omit to apply to every table")
    days_of_week: Optional[str] = Field(None, description='e.g. "sat,sun"; omit for every day')
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    priority: int = Field(0, ge=0, le=1000)
    is_active: bool = True

    @field_validator("days_of_week")
    @classmethod
    def _days(cls, v):
        return normalize_days(v)

    @model_validator(mode="after")
    def _check(self):
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError("start_time and end_time must be given together")
        self.params = normalize_params(self.rule_type, self.params)
        return self


class PricingRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    rule_type: Optional[PricingRuleType] = None
    hourly_rate: Optional[Decimal] = Field(None, gt=0, max_digits=12, decimal_places=2)
    params: Optional[dict[str, Any]] = None
    table_id: Optional[int] = None
    days_of_week: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    priority: Optional[int] = Field(None, ge=0, le=1000)
    is_active: Optional[bool] = None

    @field_validator("days_of_week")
    @classmethod
    def _days(cls, v):
        return normalize_days(v)


class PricingRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    rule_type: PricingRuleType
    hourly_rate: Optional[Decimal] = None
    params: Optional[dict[str, Any]] = None
    table_id: Optional[int] = None
    days_of_week: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    priority: int
    is_active: bool
    created_at: datetime


class PricingQuoteOut(BaseModel):
    table_id: int
    at: datetime
    minutes: int
    rule_id: Optional[int] = None
    rule_name: Optional[str] = None
    rule_type: str
    hourly_rate: Decimal
    params: dict[str, Any] = {}
    fee: Decimal