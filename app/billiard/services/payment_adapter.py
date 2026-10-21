# app/billiard/services/payment_adapter.py
# Billiard's side of the Payments contract (see app/payments/services/payable_registry.py).
#
# This is ALL billiard has to say about payments:
#   - how to find a session (tenant check + row lock)
#   - when a session may be paid (it must be stopped)
#   - how much to collect (grand_total) in which currency, for which club
#   - how to mirror the payment state back onto the session so reports stay simple
# Everything else (cash change, split, VietQR, bank feed, void, shifts) lives in app/payments.
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billiard import config
from app.billiard.models import PaymentState, SessionStatus, TableSession
from app.payments.models.order import PaymentOrder
from app.payments.services.payable_registry import Quote, payable_registry
from app.user.models.user import User

SOURCE_TYPE = "billiard_session"


class BilliardSessionPayable:
    source_type = SOURCE_TYPE

    def load(self, db: Session, source_id: str, user: Optional[User], *, lock: bool = True) -> TableSession:
        try:
            session_id = int(source_id)
        except (TypeError, ValueError):
            raise HTTPException(404, "Session not found")
        q = select(TableSession).where(TableSession.id == session_id)
        if lock:
            q = q.with_for_update()          # serializes add_item / stop / pay
        session = db.execute(q).scalar_one_or_none()
        # 404 (not 403) for other tenants: don't leak that the id exists
        if not session or (
            user is not None and not user.is_super_admin() and session.table.client_id != user.client_id
        ):
            raise HTTPException(404, "Session not found")
        return session

    def check_payable(self, session: TableSession) -> None:
        if session.status != SessionStatus.COMPLETED:
            raise HTTPException(409, "Stop the session before paying")
        # Sessions paid before the Payments module kept the bill have no order: they are settled.
        if session.payment_order_id is None and session.payment_state == PaymentState.PAID:
            raise HTTPException(409, "Session is already paid")

    def quote(self, session: TableSession) -> Quote:
        return Quote(
            client_id=session.table.client_id,
            currency=config.CURRENCY,
            total=session.grand_total,
            # Lets a human reconcile a payment with its session.
            metadata={"billiard_session_id": session.id, "table": session.table.name},
        )

    def apply_state(self, db: Session, session: TableSession, order: PaymentOrder) -> None:
        session.payment_order_id = order.id
        session.payment_state = PaymentState(order.state.value)    # unpaid | pending | paid
        session.payment_method = order.method
        session.payment_id = order.payment_id
        session.payment_reference = order.payment_reference
        session.paid_at = order.paid_at
        session.paid_by_id = order.paid_by_id


billiard_session_payable = BilliardSessionPayable()
payable_registry.register(billiard_session_payable)
