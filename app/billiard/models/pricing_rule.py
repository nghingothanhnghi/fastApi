# app/billiard/models/pricing_rule.py
import enum
from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from ._common import enum_col


class PricingRuleType(str, enum.Enum):
    PER_MINUTE = "per_minute"
    HOURLY = "hourly"
    BLOCK = "block"
    MINIMUM_HOUR = "minimum_hour"


class PricingRule(Base):
    """
    Configurable pricing. table_id NULL = applies to every table of the tenant.
    The rule actually used is copied into TableSession.pricing_snapshot at start,
    so editing/deleting a rule never rewrites history.
    """
    __tablename__ = "billiard_pricing_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    table_id: Mapped[int | None] = mapped_column(
        ForeignKey("billiard_tables.id", ondelete="CASCADE"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_type: Mapped[PricingRuleType] = mapped_column(enum_col(PricingRuleType), nullable=False)
    # Overrides the table's hourly_rate when set (e.g. weekend rate).
    hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    # Type-specific knobs, e.g. {"block_minutes": 60} or {"min_minutes": 60}.
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Optional time window, same style as HydroSchedule (club-local time).
    days_of_week: Mapped[str | None] = mapped_column(String(27), nullable=True)  # "mon,tue,..."
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)

    priority: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)  # higher wins
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())