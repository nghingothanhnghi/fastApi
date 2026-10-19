# app/billiard/models/bank_transaction.py
# Every transfer the bank feed (SePay) reports, stored before it is processed so that
# replays are harmless (UNIQUE provider + external_id) and nothing is lost for audit.
import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BankTxStatus(str, enum.Enum):
    MATCHED = "matched"            # confirmed a pending transfer line
    UNMATCHED = "unmatched"        # no bill code in the transfer content
    NEEDS_REVIEW = "needs_review"  # found a bill but something is off (amount, line already settled...)
    IGNORED = "ignored"            # not for us (outgoing, another account) or dismissed by a manager


class BankTransaction(Base):
    __tablename__ = "bank_transactions"
    __table_args__ = (UniqueConstraint("provider", "external_id", name="uq_bank_tx_provider_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)       # "sepay"
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)    # SePay transaction id

    gateway: Mapped[str | None] = mapped_column(String(60), nullable=True)  # bank name
    account_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    transfer_type: Mapped[str | None] = mapped_column(String(10), nullable=True)   # in | out
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)        # transfer memo as the bank sent it
    code: Mapped[str | None] = mapped_column(String(100), nullable=True)    # SePay's extracted payment code
    reference_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    transaction_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=BankTxStatus.UNMATCHED.value, index=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Set once a bill is identified. Unmatched rows have no tenant (the receiving account is global config).
    client_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("table_sessions.id", ondelete="SET NULL"), nullable=True)
    line_id: Mapped[int | None] = mapped_column(ForeignKey("session_payments.id", ondelete="SET NULL"), nullable=True)

    handled_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
