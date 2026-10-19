# app/billiard/models/session_payment.py
# One bill can be paid by several lines (split payment): e.g. 200k cash + 110k transfer.
# Each line is backed by a PaymentTransaction in the Payments module (payment_id).
import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, JSON, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from ._common import enum_col


class SessionPaymentStatus(str, enum.Enum):
    PENDING = "pending"        # e.g. bank transfer waiting for the cashier to confirm
    COMPLETED = "completed"    # money received
    CANCELLED = "cancelled"    # voided before the money arrived
    FAILED = "failed"          # could not be recorded


class SessionPayment(Base):
    __tablename__ = "session_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("table_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    method: Mapped[str] = mapped_column(String(30), nullable=False)          # cash | bank_transfer
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)  # part of the bill this line covers
    status: Mapped[SessionPaymentStatus] = mapped_column(
        enum_col(SessionPaymentStatus), default=SessionPaymentStatus.PENDING, nullable=False, index=True
    )

    # Cash only: what the customer handed over and the change returned.
    cash_tendered: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    change_given: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    # Bank transfer only
    transfer_memo: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_transactions.id", ondelete="SET NULL"), nullable=True
    )
    payment_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session = relationship("TableSession", back_populates="payments")


class SessionPaymentEvent(Base):
    """Append-only audit trail: who did what to a bill's payments, and when."""
    __tablename__ = "session_payment_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("table_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    line_id: Mapped[int | None] = mapped_column(
        ForeignKey("session_payments.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
