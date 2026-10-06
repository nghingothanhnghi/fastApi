# app/billiard/models/session.py
import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from ._common import enum_col


class SessionStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"   # NEW


class PaymentState(str, enum.Enum):
    UNPAID = "unpaid"
    PENDING = "pending"
    PAID = "paid"


class TableSession(Base):
    __tablename__ = "table_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # RESTRICT: a table with history can't be deleted; set is_active=False instead.
    table_id: Mapped[int] = mapped_column(
        ForeignKey("billiard_tables.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # NEW: who produced the timestamp. "device" = ESP32 clock, replayed after offline play.
    start_time_source: Mapped[str] = mapped_column(String(10), default="server", server_default="server", nullable=False)
    end_time_source: Mapped[str] = mapped_column(String(10), default="server", server_default="server", nullable=False)
    # NEW: countdown target for packages/timed play (derived display, never decremented in DB)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[SessionStatus] = mapped_column(
        enum_col(SessionStatus), default=SessionStatus.ACTIVE, nullable=False, index=True
    )

    # Snapshots taken at START
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    billing_policy: Mapped[str] = mapped_column(String(20), nullable=False)
    pricing_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # NEW: rule params used

    # NEW: package snapshot (name/price frozen when chosen)
    package_id: Mapped[int | None] = mapped_column(
        ForeignKey("billiard_packages.id", ondelete="SET NULL"), nullable=True
    )
    package_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    package_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_table_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    total_product_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), server_default="0", nullable=False)  # NEW
    grand_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)

    payment_state: Mapped[PaymentState] = mapped_column(
        enum_col(PaymentState), default=PaymentState.UNPAID, nullable=False, index=True
    )
    payment_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_transactions.id", ondelete="SET NULL"), nullable=True
    )
    payment_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Audit columns: deleting a user must not delete or block financial history.
    opened_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    stopped_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    paid_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    table = relationship("BilliardTable", back_populates="sessions")
    items = relationship(
        "SessionItem", back_populates="session", cascade="all, delete-orphan",
        lazy="selectin", order_by="SessionItem.id",
    )
    games = relationship(
        "TableGame", back_populates="session", cascade="all, delete-orphan",
        lazy="select", order_by="TableGame.game_number",
    )
    opened_by = relationship("User", foreign_keys=[opened_by_id])
    stopped_by = relationship("User", foreign_keys=[stopped_by_id])
    paid_by = relationship("User", foreign_keys=[paid_by_id])

    __table_args__ = (
        Index(
            "uq_one_active_session_per_table", "table_id", unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )