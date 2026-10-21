# app/billiard/services/payment_service.py
# Billiard's thin entry point to the Payments module. A session is paid through
# payment_order_service using source_type "billiard_session"; this class only translates a
# session id into that call and hands the refreshed session back so the route can build the bill.
#
# All payment rules (split, cash change, VietQR, bank feed, void, audit) live in app/payments.
# Like that service, these methods commit.
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.billiard.models import PaymentState, TableSession
from app.billiard.services import payment_adapter
from app.billiard.services.session_service import session_service
from app.payments.models.order import PaymentEvent
from app.payments.schemas.order import PayOrderRequest
from app.payments.services.order_service import payment_order_service
from app.user.models.user import User

SOURCE = payment_adapter.SOURCE_TYPE


def _fresh(db: Session, session_id: int, user: User) -> TableSession:
    session = session_service.get_session(db, session_id, user)
    db.refresh(session)
    return session


class BilliardPaymentService:

    @staticmethod
    def pay_session(db: Session, session_id: int, request: PayOrderRequest, user: User):
        """Returns (session, gateway). `gateway` is the Stripe payload, None for cash/transfer."""
        _, gateway = payment_order_service.pay(db, SOURCE, str(session_id), request, user)
        return _fresh(db, session_id, user), gateway

    @staticmethod
    def confirm_payment(db: Session, session_id: int, user: User) -> TableSession:
        """For gateway payments (Stripe): re-check the provider and settle the session."""
        session = session_service.get_session(db, session_id, user)
        if session.payment_order_id is None:
            if session.payment_state == PaymentState.PAID:      # settled before the Payments module
                return session
            raise HTTPException(409, "No pending gateway payment for this session")
        payment_order_service.confirm_gateway(db, SOURCE, str(session_id), user)
        return _fresh(db, session_id, user)

    @staticmethod
    def confirm_transfer(db: Session, session_id: int, line_id: int, user: User, note: Optional[str] = None):
        payment_order_service.confirm_transfer(db, SOURCE, str(session_id), line_id, user, note)
        return _fresh(db, session_id, user)

    @staticmethod
    def cancel_line(db: Session, session_id: int, line_id: int, user: User, reason: Optional[str] = None):
        payment_order_service.cancel_line(db, SOURCE, str(session_id), line_id, user, reason)
        return _fresh(db, session_id, user)

    @staticmethod
    def void_line(db: Session, session_id: int, line_id: int, user: User, reason: str):
        """Manager-only (enforced by the Payments module)."""
        payment_order_service.void_line(db, SOURCE, str(session_id), line_id, user, reason)
        return _fresh(db, session_id, user)

    @staticmethod
    def list_events(db: Session, session_id: int, user: User) -> list[PaymentEvent]:
        return payment_order_service.list_events(db, SOURCE, str(session_id), user)


billiard_payment_service = BilliardPaymentService()
