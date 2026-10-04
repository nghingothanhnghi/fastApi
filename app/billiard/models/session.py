# app/billiard/models/session.py
import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _enum(e):
    return Enum(e, values_callable=lambda x: [m.value for m in x])


class SessionStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"


class PaymentState(str, enum.Enum):
    UNPAID = "unpaid"
    PENDING = "pending"   # claimed by a /pay call, or waiting on a gateway (e.g. Stripe)
    PAID = "paid"


class TableSession(Base):
    __tablename__ = "table_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("billiard_tables.id"), nullable=False, index=True)

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[SessionStatus] = mapped_column(
        _enum(SessionStatus), default=SessionStatus.ACTIVE, nullable=False, index=True
    )

    # Snapshots taken at START: later rate/config changes never rewrite history.
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    billing_policy: Mapped[str] = mapped_column(String(20), nullable=False)

    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_table_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    total_product_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)

    # Payment
    payment_state: Mapped[PaymentState] = mapped_column(
        _enum(PaymentState), default=PaymentState.UNPAID, nullable=False, index=True
    )
    payment_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payment_transactions.id"), nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Audit: who opened / stopped / collected payment
    opened_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    stopped_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    paid_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    table = relationship("BilliardTable", back_populates="sessions")
    items = relationship(
        "SessionItem", back_populates="session", cascade="all, delete-orphan",
        lazy="selectin", order_by="SessionItem.id",
    )
    opened_by = relationship("User", foreign_keys=[opened_by_id])
    stopped_by = relationship("User", foreign_keys=[stopped_by_id])
    paid_by = relationship("User", foreign_keys=[paid_by_id])

    __table_args__ = (
        # DB-level guarantee: at most ONE active session per table (race-proof).
        Index(
            "uq_one_active_session_per_table", "table_id", unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )