# app/billiard/services/bank_feed_service.py
# Turns bank-feed transactions (SePay webhook) into confirmed transfer lines.
#
# Safety rules (SePay's own checklist + common sense about money):
#   * the raw transaction is stored first; UNIQUE(provider, external_id) makes replays no-ops
#   * only incoming transfers to OUR account are considered
#   * a line is auto-confirmed only when the memo identifies it, it is still pending, and the
#     amount is EXACTLY right. Anything else (short, over, already paid, cancelled line,
#     no code) is kept for a manager to resolve; money is never silently absorbed or invented.
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billiard import config
from app.billiard.models import BankTransaction, BankTxStatus, SessionPayment, SessionPaymentStatus, TableSession
from app.billiard.services.payment_service import billiard_payment_service
from app.billiard.services.shift_service import is_manager
from app.billiard.utils.billing import CENT
from app.user.models.user import User

logger = logging.getLogger(__name__)

PROVIDER = "sepay"
# Our memo is BIDA<session>L<line> (see vietqr.make_memo). Banks upper-case it and put other
# text around it, so search for the pattern instead of comparing the whole content.
MEMO_RE = re.compile(r"BIDA(\d+)L(\d+)(?!\d)", re.IGNORECASE)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_date(value) -> Optional[datetime]:
    """SePay sends 'YYYY-MM-DD HH:MM:SS' in Vietnam time."""
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").replace(tzinfo=config.LOCAL_TZ)
    except (TypeError, ValueError):
        return None


def _memos(*texts: Optional[str]) -> list[str]:
    found: list[str] = []
    for t in texts:
        for m in MEMO_RE.finditer(t or ""):
            memo = f"BIDA{m.group(1)}L{m.group(2)}".upper()
            if memo not in found:
                found.append(memo)
    return found


class BankFeedService:

    # ------------------------------------------------------------------ webhook

    @staticmethod
    def process_sepay(db: Session, payload: dict) -> tuple[BankTransaction, bool]:
        """Store + match one SePay transaction. Returns (row, is_duplicate). Never raises for
        business reasons (the webhook must answer success or SePay retries for 5 hours)."""
        if not isinstance(payload, dict) or payload.get("id") in (None, ""):
            raise ValueError("Payload has no transaction id")
        try:
            amount = Decimal(str(payload.get("transferAmount"))).quantize(CENT)
        except (InvalidOperation, TypeError):
            raise ValueError("Invalid transferAmount")
        external_id = str(payload["id"])

        existing = db.query(BankTransaction).filter_by(provider=PROVIDER, external_id=external_id).first()
        if existing:
            return existing, True

        tx = BankTransaction(
            provider=PROVIDER, external_id=external_id,
            gateway=payload.get("gateway"), account_number=payload.get("accountNumber"),
            transfer_type=(payload.get("transferType") or "").lower() or None,
            amount=amount, content=payload.get("content"), code=payload.get("code"),
            reference_code=payload.get("referenceCode"),
            transaction_date=_parse_date(payload.get("transactionDate")),
            raw=payload, status=BankTxStatus.UNMATCHED.value,
        )
        db.add(tx)
        try:
            db.commit()                      # the claim: a concurrent replay hits the unique constraint
        except IntegrityError:
            db.rollback()
            again = db.query(BankTransaction).filter_by(provider=PROVIDER, external_id=external_id).one()
            return again, True

        try:
            BankFeedService._match(db, tx.id)
        except Exception:
            # Keep the stored row for a human; answer success so SePay does not retry.
            logger.exception("SePay transaction %s: matching failed", external_id)
            db.rollback()
            tx = db.get(BankTransaction, tx.id)
            tx.status = BankTxStatus.NEEDS_REVIEW.value
            tx.reason = "Automatic matching failed; check the logs"
            db.commit()
        return db.get(BankTransaction, tx.id), False

    @staticmethod
    def _set(db: Session, tx: BankTransaction, status: BankTxStatus, reason: Optional[str],
             line: Optional[SessionPayment] = None) -> None:
        tx.status = status.value
        tx.reason = reason
        if line is not None:
            tx.line_id = line.id
            tx.session_id = line.session_id
            tx.client_id = line.session.table.client_id
        db.commit()

    @staticmethod
    def _match(db: Session, tx_id: int) -> None:
        tx = db.get(BankTransaction, tx_id)

        if tx.transfer_type != "in":
            return BankFeedService._set(db, tx, BankTxStatus.IGNORED, "Outgoing transfer")
        if config.BANK_ACCOUNT_NO and (tx.account_number or "") != config.BANK_ACCOUNT_NO:
            return BankFeedService._set(db, tx, BankTxStatus.IGNORED, "Received on a different account")

        memos = _memos(tx.content, tx.code)
        if not memos:
            return BankFeedService._set(db, tx, BankTxStatus.UNMATCHED, "No bill code in the transfer content")

        line = (
            db.query(SessionPayment)
            .filter(func.upper(SessionPayment.transfer_memo).in_(memos))
            .order_by(SessionPayment.id)
            .first()
        )
        if line is None:
            return BankFeedService._set(db, tx, BankTxStatus.UNMATCHED, f"No payment line for code {memos[0]}")

        if line.status == SessionPaymentStatus.COMPLETED:
            return BankFeedService._set(
                db, tx, BankTxStatus.NEEDS_REVIEW,
                "This bill line was already paid: possible duplicate transfer (refund the customer?)", line)
        if line.status != SessionPaymentStatus.PENDING:
            return BankFeedService._set(
                db, tx, BankTxStatus.NEEDS_REVIEW,
                f"Money received for a line that is {line.status.value}", line)
        if tx.amount != line.amount:
            return BankFeedService._set(
                db, tx, BankTxStatus.NEEDS_REVIEW,
                f"Amount mismatch: expected {line.amount}, received {tx.amount}", line)

        try:
            BankFeedService._confirm(db, tx, line, actor=None)
        except HTTPException as e:
            # Lost a race (the line was settled between our check and the lock): keep it for review.
            db.rollback()
            tx = db.get(BankTransaction, tx_id)
            BankFeedService._set(db, tx, BankTxStatus.NEEDS_REVIEW, f"Could not confirm the line: {e.detail}",
                                 db.get(SessionPayment, line.id))

    @staticmethod
    def _confirm(db: Session, tx: BankTransaction, line: SessionPayment, actor: Optional[User]) -> None:
        details = {"gateway": tx.gateway, "reference_code": tx.reference_code, "bank_amount": str(tx.amount)}
        billiard_payment_service.confirm_transfer_from_bank(
            db, line.session_id, line.id, tx.id, details, actor=actor,
        )
        tx = db.get(BankTransaction, tx.id)
        line = db.get(SessionPayment, line.id)
        tx.status = BankTxStatus.MATCHED.value
        tx.reason = None
        tx.line_id, tx.session_id = line.id, line.session_id
        tx.client_id = line.session.table.client_id
        if actor is not None:
            tx.handled_by_id, tx.handled_at = actor.id, _now()
        db.commit()

    # ------------------------------------------------------ manager workflow

    @staticmethod
    def _require_manager(user: User) -> None:
        if not is_manager(user):
            raise HTTPException(403, "Only a manager can handle bank transactions")

    @staticmethod
    def _visible(tx: BankTransaction, user: User) -> bool:
        # Matched rows carry their club; unmatched ones have none (global receiving account).
        return user.is_super_admin() or tx.client_id is None or tx.client_id == user.client_id

    @staticmethod
    def list_transactions(db: Session, user: User, status: Optional[str] = None,
                          limit: int = 50, offset: int = 0) -> list[BankTransaction]:
        BankFeedService._require_manager(user)
        q = db.query(BankTransaction)
        if not user.is_super_admin():
            q = q.filter((BankTransaction.client_id.is_(None)) | (BankTransaction.client_id == user.client_id))
        if status:
            q = q.filter(BankTransaction.status == status)
        return q.order_by(BankTransaction.id.desc()).offset(offset).limit(min(max(limit, 1), 200)).all()

    @staticmethod
    def _get(db: Session, tx_id: int, user: User) -> BankTransaction:
        tx = db.get(BankTransaction, tx_id)
        if not tx or not BankFeedService._visible(tx, user):
            raise HTTPException(404, "Bank transaction not found")
        return tx

    @staticmethod
    def assign(db: Session, tx_id: int, line_id: int, user: User) -> BankTransaction:
        """Manager links an unmatched / flagged transaction to a pending transfer line."""
        BankFeedService._require_manager(user)
        tx = BankFeedService._get(db, tx_id, user)
        if tx.status not in (BankTxStatus.UNMATCHED.value, BankTxStatus.NEEDS_REVIEW.value):
            raise HTTPException(409, f"Transaction is already {tx.status}")
        if tx.transfer_type != "in":
            raise HTTPException(409, "Only incoming transfers can be assigned")

        line = db.get(SessionPayment, line_id)
        session = db.get(TableSession, line.session_id) if line else None
        if not line or (not user.is_super_admin() and session.table.client_id != user.client_id):
            raise HTTPException(404, "Payment line not found")
        if line.method != "bank_transfer" or line.status != SessionPaymentStatus.PENDING:
            raise HTTPException(409, "The line must be a pending bank transfer")
        if tx.amount != line.amount:
            raise HTTPException(
                422, f"Amount differs (line {line.amount}, bank {tx.amount}). "
                     "Settle the difference with the customer, then ignore this transaction.")

        BankFeedService._confirm(db, tx, line, actor=user)
        return db.get(BankTransaction, tx_id)

    @staticmethod
    def ignore(db: Session, tx_id: int, user: User, note: Optional[str]) -> BankTransaction:
        BankFeedService._require_manager(user)
        tx = BankFeedService._get(db, tx_id, user)
        if tx.status not in (BankTxStatus.UNMATCHED.value, BankTxStatus.NEEDS_REVIEW.value):
            raise HTTPException(409, f"Transaction is already {tx.status}")
        tx.status = BankTxStatus.IGNORED.value
        tx.note = note
        tx.handled_by_id, tx.handled_at = user.id, _now()
        db.commit()
        db.refresh(tx)
        return tx


bank_feed_service = BankFeedService()
