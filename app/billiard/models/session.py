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


# Billing review: a device asked for a package the server could not apply. The session is real and billed
# as played, but payment is blocked until someone assigns a valid package or confirms normal pricing.
BILLING_REVIEW_REQUIRED = "required"
BILLING_REVIEW_RESOLVED = "resolved"
REVIEW_ASSIGN_PACKAGE = "assign_package"
REVIEW_CONFIRM_NORMAL = "confirm_normal_pricing"


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
    # Everything billing needs from the package, frozen at start (editing the package later changes nothing):
    # {package_id, name, price, duration_minutes, items: [{product_id, included_quantity}]}. None = no package.
    package_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Billing review (see BILLING_REVIEW_* above). requested_package_id is what the DEVICE asked for: kept as a plain
    # number, never a foreign key, because it may be unknown or another club's. It is separate from package_snapshot
    # (what the customer was actually sold) so a device event can never overwrite the purchased terms.
    billing_review_state: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    requested_package_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    billing_review_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    billing_review_resolution: Mapped[str | None] = mapped_column(String(30), nullable=True)
    billing_review_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    billing_reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    billing_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Self-contained audit of the decision: action, resolver roles at that moment, the request and reason, and the
    # bill BEFORE and AFTER (fees, discount, total, package). Written once, by session_lifecycle.resolve_billing_review.
    billing_review_audit: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_table_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    total_product_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), server_default="0", nullable=False)  # NEW
    grand_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)

    payment_state: Mapped[PaymentState] = mapped_column(
        enum_col(PaymentState), default=PaymentState.UNPAID, nullable=False, index=True
    )
    payment_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # The bill in the Payments module (lines, transfers, audit). payment_state/method/id/reference/
    # paid_* above are a mirror of it, written by BilliardSessionPayable.apply_state, so reports
    # and the bill never have to join the Payments tables to know whether a session is paid.
    payment_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_orders.id", ondelete="SET NULL"), nullable=True
    )
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_transactions.id", ondelete="SET NULL"), nullable=True
    )
    payment_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Audit columns: deleting a user must not delete or block financial history.
    opened_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    stopped_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    paid_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Discount audit. `discount` (above) is the AMOUNT applied; the intended percent/fixed value
    # lives in pricing_snapshot["discount"] so it can follow the final fee at Stop.
    discount_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    discounted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Cancel = "opened by mistake": no bill, no payment. Set only by session_lifecycle.cancel_session.
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    table = relationship("BilliardTable", back_populates="sessions")
    items = relationship(
        "SessionItem", back_populates="session", cascade="all, delete-orphan",
        lazy="selectin", order_by="SessionItem.id",
    )
    payment_order = relationship("PaymentOrder", lazy="selectin")
    games = relationship(
        "TableGame", back_populates="session", cascade="all, delete-orphan",
        lazy="select", order_by="TableGame.game_number",
    )
    opened_by = relationship("User", foreign_keys=[opened_by_id])
    stopped_by = relationship("User", foreign_keys=[stopped_by_id])
    paid_by = relationship("User", foreign_keys=[paid_by_id])
    cancelled_by = relationship("User", foreign_keys=[cancelled_by_id])
    discounted_by = relationship("User", foreign_keys=[discounted_by_id])
    billing_reviewed_by = relationship("User", foreign_keys=[billing_reviewed_by_id])

    __table_args__ = (
        Index(
            "uq_one_active_session_per_table", "table_id", unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )