# app/billiard/services/payment_service.py
# Bridges a completed billiard session to the existing Payment module.
#
# NOTE: unlike the other billiard services, this one commits. The Payment
# providers (manual_service / stripe_service) call db.commit() themselves, so a
# single wrapping transaction is impossible. Instead we use a claim pattern:
#   1. lock session, flip payment_state UNPAID -> PENDING, commit  (the "claim")
#   2. call the provider (concurrent /pay calls now get 409)
#   3. on success mark PAID (manual) or leave PENDING (gateway); on error release the claim
import logging
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.billiard import config
from app.billiard.models import TableSession, SessionStatus, PaymentState
from app.billiard.services.session_service import session_service
from app.payments.services.provider_registry import payment_provider_registry
from app.user.models.user import User

logger = logging.getLogger(__name__)


def _split(result):
    """manual -> PaymentOut ; stripe -> {"payment": PaymentOut, "stripe": {...}}"""
    if isinstance(result, dict):
        return result["payment"], result.get("stripe")
    return result, None


def _is_completed(payment) -> bool:
    return getattr(payment.status, "value", payment.status) == "completed"


def _release_claim(db: Session, session_id: int) -> None:
    db.query(TableSession).filter(
        TableSession.id == session_id,
        TableSession.payment_state == PaymentState.PENDING,
        TableSession.payment_id.is_(None),
    ).update({"payment_state": PaymentState.UNPAID, "payment_method": None}, synchronize_session=False)
    db.commit()


def _mark_paid(session: TableSession, user: User) -> None:
    session.payment_state = PaymentState.PAID
    session.paid_at = datetime.now(timezone.utc)
    session.paid_by_id = user.id


class BilliardPaymentService:

    @staticmethod
    def pay_session(db: Session, session_id: int, method: str, user: User):
        provider_name = config.PAYMENT_METHODS[method]

        session = session_service.get_locked_session(db, session_id, user)
        if session.status != SessionStatus.COMPLETED:
            raise HTTPException(409, "Stop the session before paying")
        if session.payment_state == PaymentState.PAID:
            raise HTTPException(409, "Session is already paid")
        if session.payment_state == PaymentState.PENDING:
            raise HTTPException(409, "A payment for this session is already in progress")
        if session.grand_total <= 0:
            raise HTTPException(409, "Nothing to pay")

        # Capture before commit() expires the instance
        amount = float(session.grand_total)   # PaymentTransaction.amount is Float
        client_id = session.table.client_id
        table_name = session.table.name

        session.payment_state = PaymentState.PENDING
        session.payment_method = method
        db.commit()                           # the claim

        try:
            provider = payment_provider_registry.get_provider(provider_name)
            result = provider.create_payment(
                db,
                user_id=user.id,
                client_id=client_id,
                amount=amount,
                currency=config.CURRENCY,
                extra_metadata={"billiard_session_id": session_id, "table": table_name, "method": method},
            )
            payment, gateway = _split(result)
            if provider_name == "manual":     # cash / bank transfer: collected at the counter
                payment = provider.confirm_payment(db, payment.reference_id)
        except Exception:
            db.rollback()
            _release_claim(db, session_id)
            raise

        try:
            session = session_service.get_locked_session(db, session_id, user)
            session.payment_id = payment.id
            session.payment_reference = payment.reference_id
            if _is_completed(payment):
                _mark_paid(session, user)
            db.commit()
        except Exception:
            # Payment exists but bookkeeping failed: reconcile via billiard_session_id in metadata.
            logger.exception("Billiard session %s: payment %s recorded but session update failed",
                             session_id, getattr(payment, "reference_id", None))
            db.rollback()
            raise

        db.refresh(session)
        return session, gateway

    @staticmethod
    def confirm_payment(db: Session, session_id: int, user: User):
        """For gateway payments (Stripe): re-check the provider and settle the session."""
        session = session_service.get_locked_session(db, session_id, user)
        if session.payment_state == PaymentState.PAID:
            return session
        if session.payment_state != PaymentState.PENDING or not session.payment_reference:
            raise HTTPException(409, "No pending gateway payment for this session")

        provider = payment_provider_registry.get_provider(config.PAYMENT_METHODS[session.payment_method])
        payment = provider.confirm_payment(db, session.payment_reference)   # commits internally
        if payment is None:
            raise HTTPException(404, "Payment transaction not found")

        session = session_service.get_locked_session(db, session_id, user)
        status = getattr(payment.status, "value", payment.status)
        if status == "completed":
            _mark_paid(session, user)
        elif status in ("failed", "refunded"):   # let the cashier retry
            session.payment_state = PaymentState.UNPAID
            session.payment_id = None
            session.payment_reference = None
            session.payment_method = None
        db.commit()
        db.refresh(session)
        return session


billiard_payment_service = BilliardPaymentService()