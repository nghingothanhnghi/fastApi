# app/payments/models/order.py
# A PaymentOrder is "the bill" of any business object (a billiard session, a shop order, ...),
# identified by (source_type, source_id). It can be paid by several lines (split payment),
# e.g. 200k cash + 110k transfer. Each line is backed by a PaymentTransaction (payment_id).
#
# The business module owns the amount and the object; this module owns everything about how
# it gets paid. See app/payments/services/payable_registry.py for the contract.
import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, JSON, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from ._common import enum_col


class PaymentOrderState(str, enum.Enum):
    UNPAID = "unpaid"
    PENDING = "pending"   # a payment is in progress: a transfer waiting, part paid, or a gateway payment
    PAID = "paid"


class PaymentLineStatus(str, enum.Enum):
    PENDING = "pending"        # e.g. bank transfer waiting for the cashier / bank feed to confirm
    COMPLETED = "completed"    # money received
    VOIDED = "voided"          # was received, then reversed by a manager
    CANCELLED = "cancelled"    # voided before the money arrived
    FAILED = "failed"          # could not be recorded


class PaymentOrder(Base):
    __tablename__ = "payment_orders"
    __table_args__ = (UniqueConstraint("source_type", "source_id", name="uq_payment_order_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[str] = mapped_column(String, nullable=False, index=True)   # tenant, set by the business
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)         # e.g. "billiard_session"
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)

    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)       # snapshot of what the business asked to collect

    state: Mapped[PaymentOrderState] = mapped_column(
        enum_col(PaymentOrderState), default=PaymentOrderState.UNPAID, nullable=False, index=True
    )
    method: Mapped[str | None] = mapped_column(String(30), nullable=True)        # cash | bank_transfer | stripe | split
    # First completed payment (Payments module record), kept for quick links and receipts.
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_transactions.id", ondelete="SET NULL"), nullable=True
    )
    payment_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    lines = relationship(
        "PaymentLine", back_populates="order", cascade="all, delete-orphan",
        lazy="selectin", order_by="PaymentLine.id",
    )


class PaymentLine(Base):
    __tablename__ = "payment_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("payment_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    method: Mapped[str] = mapped_column(String(30), nullable=False)          # cash | bank_transfer
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)  # part of the bill this line covers
    status: Mapped[PaymentLineStatus] = mapped_column(
        enum_col(PaymentLineStatus), default=PaymentLineStatus.PENDING, nullable=False, index=True
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

    # Manager void of a completed line (money handed back / transfer returned)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    order = relationship("PaymentOrder", back_populates="lines")


class PaymentEvent(Base):
    """Append-only audit trail: who did what to an order's payments, and when."""
    __tablename__ = "payment_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("payment_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    line_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_lines.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
