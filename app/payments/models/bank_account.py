"""Per-club receiving bank accounts used to build bank-transfer QR codes.

Rules
- A club has at most ONE active account (partial unique index).
- Payout fields (bin / account_no / account_name) are immutable. To change them,
  create a new account; the old one is deactivated, not edited. Pending
  PaymentLines keep pointing at the account they showed to the customer.
- The same bank account cannot be active in two clubs (bank feed matching
  would become ambiguous).
"""
from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, text,
)
from sqlalchemy.orm import Mapped, mapped_column

# NOTE: adjust this import to wherever your Base lives (same one order.py uses).
from app.database import Base


def _utcnow() -> datetime:
    """Naive UTC, matching the rest of the schema, without the deprecated utcnow()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PaymentBankAccount(Base):
    __tablename__ = "payment_bank_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    bank_bin: Mapped[str] = mapped_column(String(10), nullable=False)
    bank_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    account_no: Mapped[str] = mapped_column(String(32), nullable=False)
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="1"
    )
    created_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        Index(
            "uq_one_active_bank_account_per_club", "client_id",
            unique=True,
            sqlite_where=text("is_active = 1"),
            postgresql_where=text("is_active IS TRUE"),
        ),
        Index(
            "uq_active_bank_account_number", "bank_bin", "account_no",
            unique=True,
            sqlite_where=text("is_active = 1"),
            postgresql_where=text("is_active IS TRUE"),
        ),
    )


class PaymentBankAccountEvent(Base):
    """Audit trail: who created / replaced / renamed / deactivated an account."""
    __tablename__ = "payment_bank_account_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_bank_accounts.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
