# app/billiard/services/payment_service.py
# Bridges a completed billiard session to the existing Payment module.
#
# A bill is paid by one or more "lines" (SessionPayment): cash, bank transfer (VietQR),
# or a single Stripe gateway payment. Each cash/transfer line is backed by a
# PaymentTransaction created through the manual provider.
#
# NOTE: unlike the other billiard services, this one commits. The Payment
# providers (manual_service / stripe_service) call db.commit() themselves, so a
# single wrapping transaction is impossible. Instead we use a claim pattern:
#   1. lock session, insert the lines, flip payment_state UNPAID -> PENDING, commit  (the "claim")
#   2. call the provider per line (concurrent /pay calls now get 409)
#   3. settle: PAID when completed lines cover grand_total; a transfer line waiting for the
#      cashier keeps the session PENDING; if nothing was collected, release back to UNPAID
# Anything left half-done is visible on the bill (line statuses) and recoverable by
# confirming or cancelling the pending line.
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.billiard import config
from app.billiard.models import (
    TableSession, SessionStatus, PaymentState,
    SessionPayment, SessionPaymentEvent, SessionPaymentStatus,
)
from app.billiard.schemas.session import PaySessionRequest
from app.billiard.services.session_service import session_service
from app.billiard.utils.billing import CENT
from app.billiard.utils.vietqr import make_memo
from app.payments.schemas.payment import PaymentStatus, PaymentUpdate
from app.payments.services.payment_service import payment_service
from app.payments.services.provider_registry import payment_provider_registry
from app.user.models.user import User

logger = logging.getLogger(__name__)

LineStatus = SessionPaymentStatus


@dataclass
class LineSpec:
    method: str
    amount: Decimal
    cash_tendered: Optional[Decimal] = None
    note: Optional[str] = None


def _split(result):
    """manual -> PaymentOut ; stripe -> {"payment": PaymentOut, "stripe": {...}}"""
    if isinstance(result, dict):
        return result["payment"], result.get("stripe")
    return result, None


def _is_completed(payment) -> bool:
    return getattr(payment.status, "value", payment.status) == "completed"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _log(db: Session, session_id: int, event_type: str, actor_id: Optional[int],
         line_id: Optional[int] = None, data: Optional[dict] = None) -> None:
    db.add(SessionPaymentEvent(
        session_id=session_id, line_id=line_id, event_type=event_type, actor_id=actor_id, data=data,
    ))


def _amount_paid(session: TableSession) -> Decimal:
    return sum((p.amount for p in session.payments if p.status == LineStatus.COMPLETED), Decimal("0"))


def _balance_due(session: TableSession) -> Decimal:
    return (session.grand_total - _amount_paid(session)).quantize(CENT)


def _method_label(session: TableSession) -> Optional[str]:
    methods = {p.method for p in session.payments if p.status in (LineStatus.COMPLETED, LineStatus.PENDING)}
    if not methods:
        return None
    return methods.pop() if len(methods) == 1 else "split"


def _mark_paid(session: TableSession, user: User) -> None:
    session.payment_state = PaymentState.PAID
    session.paid_at = _now()
    session.paid_by_id = user.id


def _release_claim(db: Session, session_id: int) -> None:
    db.query(TableSession).filter(
        TableSession.id == session_id,
        TableSession.payment_state == PaymentState.PENDING,
        TableSession.payment_id.is_(None),
    ).update({"payment_state": PaymentState.UNPAID, "payment_method": None}, synchronize_session=False)
    db.commit()


def _settle(db: Session, session: TableSession, user: User) -> None:
    """Derive payment_state from the lines. Caller commits."""
    open_lines = [p for p in session.payments if p.status == LineStatus.PENDING]
    completed = [p for p in session.payments if p.status == LineStatus.COMPLETED]
    session.payment_method = _method_label(session)

    if completed:
        session.payment_id = completed[0].payment_id
        session.payment_reference = completed[0].payment_reference

    if not open_lines and _balance_due(session) <= 0:
        if session.payment_state != PaymentState.PAID:
            _mark_paid(session, user)
            _log(db, session.id, "session_paid", user.id,
                 data={"amount": str(session.grand_total), "method": session.payment_method})
    elif not open_lines and not completed:
        # Nothing collected and nothing waiting: let the cashier start over.
        session.payment_state = PaymentState.UNPAID
        session.payment_method = None
        session.payment_id = None
        session.payment_reference = None
    else:
        session.payment_state = PaymentState.PENDING


def _find_line(session: TableSession, line_id: int) -> SessionPayment:
    line = next((p for p in session.payments if p.id == line_id), None)
    if not line:
        raise HTTPException(404, "Payment line not found")
    return line


def _specs(request: PaySessionRequest, balance: Decimal) -> list[LineSpec]:
    if request.payments:
        return [
            LineSpec(p.method, Decimal(p.amount).quantize(CENT), p.cash_tendered, p.note)
            for p in request.payments
        ]
    return [LineSpec(request.payment_method, balance, request.cash_tendered)]


def _validate_specs(specs: list[LineSpec], balance: Decimal) -> None:
    total = sum((s.amount for s in specs), Decimal("0")).quantize(CENT)
    if total != balance:
        raise HTTPException(422, f"Payment lines add up to {total} but the amount due is {balance}")
    for s in specs:
        if s.method == "cash":
            tendered = s.cash_tendered if s.cash_tendered is not None else s.amount
            if tendered < s.amount:
                raise HTTPException(422, f"Cash tendered {tendered} is less than the cash amount {s.amount}")


class BilliardPaymentService:

    # ------------------------------------------------------------------ pay

    @staticmethod
    def pay_session(db: Session, session_id: int, request: PaySessionRequest, user: User):
        session = session_service.get_locked_session(db, session_id, user)
        if session.status != SessionStatus.COMPLETED:
            raise HTTPException(409, "Stop the session before paying")
        if session.payment_state == PaymentState.PAID:
            raise HTTPException(409, "Session is already paid")
        if session.grand_total <= 0:
            raise HTTPException(409, "Nothing to pay")

        if request.payment_method == "stripe":
            return BilliardPaymentService._pay_gateway(db, session, user)

        if session.payment_state == PaymentState.PENDING:
            open_lines = [p for p in session.payments if p.status == LineStatus.PENDING]
            if open_lines or not session.payments:
                raise HTTPException(409, "A payment for this session is already in progress")
            # Only completed lines so far (e.g. a transfer was cancelled): pay the rest.

        balance = _balance_due(session)
        if balance <= 0:
            raise HTTPException(409, "Nothing to pay")
        specs = _specs(request, balance)
        _validate_specs(specs, balance)

        # --- phase 1: the claim ---------------------------------------------------
        for s in specs:
            tendered = change = None
            if s.method == "cash":
                tendered = s.cash_tendered if s.cash_tendered is not None else s.amount
                change = (tendered - s.amount).quantize(CENT)
            session.payments.append(SessionPayment(
                method=s.method, amount=s.amount, status=LineStatus.PENDING,
                cash_tendered=tendered, change_given=change, note=s.note, created_by_id=user.id,
            ))
        db.flush()                                   # assign line ids
        for line in session.payments:
            if line.status == LineStatus.PENDING and line.method == "bank_transfer" and not line.transfer_memo:
                line.transfer_memo = make_memo(session.id, line.id)
                line.expires_at = _now() + timedelta(minutes=config.TRANSFER_EXPIRE_MINUTES)
            if line.status == LineStatus.PENDING:
                _log(db, session.id, "line_created", user.id, line.id,
                     {"method": line.method, "amount": str(line.amount)})
        session.payment_state = PaymentState.PENDING
        session.payment_method = _method_label(session)

        new_ids = [p.id for p in session.payments if p.status == LineStatus.PENDING and p.payment_id is None]
        client_id = session.table.client_id
        table_name = session.table.name
        db.commit()                                  # expires the instances below

        # --- phase 2: one provider payment per line ---------------------------------
        provider = payment_provider_registry.get_provider("manual")
        failed_at: Optional[int] = None
        for idx, line_id in enumerate(new_ids):
            try:
                line = db.get(SessionPayment, line_id)
                method, amount = line.method, line.amount
                result = provider.create_payment(
                    db,
                    user_id=user.id,
                    client_id=client_id,
                    amount=float(amount),             # PaymentTransaction.amount is Float
                    currency=config.CURRENCY,
                    extra_metadata={
                        "billiard_session_id": session_id, "table": table_name,
                        "method": method, "line_id": line_id,
                    },
                )
                payment, _ = _split(result)
                line = db.get(SessionPayment, line_id)
                line.payment_id = payment.id
                line.payment_reference = payment.reference_id
                auto = method == "cash" or not config.BANK_TRANSFER_REQUIRES_CONFIRMATION
                if auto:
                    provider.confirm_payment(db, payment.reference_id)   # commits
                    line = db.get(SessionPayment, line_id)
                    line.status = LineStatus.COMPLETED
                    line.confirmed_by_id = user.id
                    line.confirmed_at = _now()
                    _log(db, session_id, "cash_received" if method == "cash" else "transfer_confirmed",
                         user.id, line_id, {"amount": str(line.amount),
                                            "cash_tendered": str(line.cash_tendered) if line.cash_tendered is not None else None,
                                            "change_given": str(line.change_given) if line.change_given is not None else None})
                else:
                    _log(db, session_id, "transfer_awaiting", user.id, line_id,
                         {"amount": str(line.amount), "memo": line.transfer_memo})
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("Billiard session %s: recording payment line %s failed", session_id, line_id)
                failed_at = idx
                break

        if failed_at is not None:
            # Mark the failed line and any not-yet-processed ones so nothing looks "awaiting".
            for line_id in new_ids[failed_at:]:
                line = db.get(SessionPayment, line_id)
                if line is not None and line.status == LineStatus.PENDING and line.payment_id is None:
                    line.status = LineStatus.FAILED
                    _log(db, session_id, "line_failed", user.id, line_id)
            db.commit()

        session = session_service.get_locked_session(db, session_id, user)
        _settle(db, session, user)
        db.commit()

        if failed_at is not None:
            raise HTTPException(500, "Some payment lines could not be recorded; check the bill and retry the balance")

        session = session_service.get_locked_session(db, session_id, user)
        db.refresh(session)
        return session, None

    # --------------------------------------------------------------- gateway

    @staticmethod
    def _pay_gateway(db: Session, session: TableSession, user: User):
        """Stripe: a single payment for the whole bill, settled later by /pay/confirm."""
        if session.payment_state == PaymentState.PENDING:
            raise HTTPException(409, "A payment for this session is already in progress")
        if session.payments:
            raise HTTPException(409, "This session already has cash/transfer payments; pay the balance with those methods")

        session_id = session.id
        provider_name = config.PAYMENT_METHODS["stripe"]
        amount = float(session.grand_total)   # PaymentTransaction.amount is Float
        client_id = session.table.client_id
        table_name = session.table.name

        session.payment_state = PaymentState.PENDING
        session.payment_method = "stripe"
        db.commit()                           # the claim

        try:
            provider = payment_provider_registry.get_provider(provider_name)
            result = provider.create_payment(
                db,
                user_id=user.id,
                client_id=client_id,
                amount=amount,
                currency=config.CURRENCY,
                extra_metadata={"billiard_session_id": session_id, "table": table_name, "method": "stripe"},
            )
            payment, gateway = _split(result)
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
        if (session.payment_state != PaymentState.PENDING or not session.payment_reference
                or session.payment_method != "stripe"):
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

    # --------------------------------------------------- transfer line actions

    @staticmethod
    def confirm_transfer(db: Session, session_id: int, line_id: int, user: User, note: Optional[str] = None):
        """Cashier confirms the bank transfer arrived (the manual 'received' tick)."""
        session = session_service.get_locked_session(db, session_id, user)
        line = _find_line(session, line_id)
        if line.method != "bank_transfer":
            raise HTTPException(409, "Only bank transfer lines are confirmed this way")
        if line.status == LineStatus.COMPLETED:
            return session                                  # idempotent
        if line.status != LineStatus.PENDING:
            raise HTTPException(409, f"Payment line is {line.status.value}")

        reference = line.payment_reference
        if reference:
            manual = payment_provider_registry.get_provider("manual")
            if manual.confirm_payment(db, reference) is None:    # commits internally
                raise HTTPException(404, "Payment transaction not found")

        session = session_service.get_locked_session(db, session_id, user)
        line = _find_line(session, line_id)
        line.status = LineStatus.COMPLETED
        line.confirmed_by_id = user.id
        line.confirmed_at = _now()
        if note:
            line.note = note
        _log(db, session_id, "transfer_confirmed", user.id, line_id,
             {"amount": str(line.amount), "memo": line.transfer_memo, "note": note})
        _settle(db, session, user)
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def cancel_line(db: Session, session_id: int, line_id: int, user: User, reason: Optional[str] = None):
        """Void a line that is still waiting (e.g. the customer decided to pay cash instead)."""
        session = session_service.get_locked_session(db, session_id, user)
        line = _find_line(session, line_id)
        if line.status != LineStatus.PENDING:
            raise HTTPException(409, "Only a pending payment line can be cancelled")

        payment_id = line.payment_id
        if payment_id:
            existing = payment_service.get_payment(db, payment_id)
            meta = {**(existing.extra_metadata or {}), "cancelled": True, "cancel_reason": reason} if existing else None
            payment_service.update_payment_status(
                db, payment_id, PaymentUpdate(status=PaymentStatus.FAILED, extra_metadata=meta),
            )                                               # commits internally; keeps billiard_session_id

        session = session_service.get_locked_session(db, session_id, user)
        line = _find_line(session, line_id)
        line.status = LineStatus.CANCELLED
        if reason:
            line.note = reason
        _log(db, session_id, "line_cancelled", user.id, line_id, {"reason": reason})
        _settle(db, session, user)
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def list_events(db: Session, session_id: int, user: User) -> list[SessionPaymentEvent]:
        session_service.get_session(db, session_id, user)   # tenant check
        return (
            db.query(SessionPaymentEvent)
            .filter(SessionPaymentEvent.session_id == session_id)
            .order_by(SessionPaymentEvent.id)
            .all()
        )


billiard_payment_service = BilliardPaymentService()
