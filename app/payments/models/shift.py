# app/payments/models/shift.py
# A shift is one cashier's turn on the cash drawer. One drawer per club (client_id):
# at most one shift is open at a time. Cash taken/voided during the open window is
# derived from payment_lines; pay-ins and pay-outs are recorded as movements.
import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from ._common import enum_col


class ShiftStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"


class MovementType(str, enum.Enum):
    PAY_IN = "pay_in"      # cash put into the drawer (e.g. extra change from the safe)
    PAY_OUT = "pay_out"    # cash taken out (e.g. buying ice, paying a supplier)


class CashShift(Base):
    __tablename__ = "cash_shifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[ShiftStatus] = mapped_column(
        enum_col(ShiftStatus), default=ShiftStatus.OPEN, nullable=False, index=True
    )

    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opening_float: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)

    # Frozen at close so a closed shift never changes.
    expected_cash: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    counted_cash: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    variance: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)   # counted - expected

    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    close_note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    opened_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    closed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    opened_by = relationship("User", foreign_keys=[opened_by_id])
    closed_by = relationship("User", foreign_keys=[closed_by_id])
    movements = relationship(
        "CashMovement", back_populates="shift", cascade="all, delete-orphan",
        lazy="selectin", order_by="CashMovement.id",
    )

    __table_args__ = (
        Index(
            "uq_one_open_shift_per_client", "client_id", unique=True,
            sqlite_where=text("status = 'open'"),
            postgresql_where=text("status = 'open'"),
        ),
    )


class CashMovement(Base):
    __tablename__ = "cash_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_id: Mapped[int] = mapped_column(
        ForeignKey("cash_shifts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[MovementType] = mapped_column(enum_col(MovementType), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    shift = relationship("CashShift", back_populates="movements")
    created_by = relationship("User", foreign_keys=[created_by_id])
