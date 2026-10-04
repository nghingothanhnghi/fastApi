# app/billiard/routes/session_router.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.user.models.user import User
from app.user.utils.token import get_current_user
from app.billiard.schemas.session import (
    AddSessionItemRequest, BillResponse, PayResponse, PaySessionRequest, SessionItemResponse,
)
from app.billiard.services.payment_service import billiard_payment_service
from app.billiard.services.session_service import session_service

router = APIRouter(prefix="/sessions", tags=["Billiard Sessions"])


@router.get("/{session_id}", response_model=BillResponse)
def get_bill(session_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Re-print a bill / receipt at any time (built from snapshots)."""
    return session_service.build_bill(session_service.get_session(db, session_id, current_user))


@router.post("/{session_id}/items", response_model=SessionItemResponse, status_code=201)
def add_item(
    session_id: int, request: AddSessionItemRequest,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    item = session_service.add_item(
        db, session_id, request.product_id, request.quantity, request.variant_id, current_user
    )
    db.commit()
    return SessionItemResponse(
        id=item.id, product_id=item.product_id, variant_id=item.variant_id,
        product_name=item.product_name, quantity=item.quantity,
        unit_price=item.unit_price, total_price=item.total_price,
    )


@router.post("/{session_id}/stop", response_model=BillResponse)
def stop_session(session_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    session = session_service.stop_session(db, session_id, current_user)
    db.commit()
    db.refresh(session)
    return session_service.build_bill(session)


@router.post("/{session_id}/pay", response_model=PayResponse)
def pay_session(
    session_id: int, request: PaySessionRequest,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    session, gateway = billiard_payment_service.pay_session(db, session_id, request.payment_method, current_user)
    return {**session_service.build_bill(session), "gateway": gateway}


@router.post("/{session_id}/pay/confirm", response_model=BillResponse)
def confirm_payment(session_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Settle a gateway (Stripe) payment after the customer completes it."""
    session = billiard_payment_service.confirm_payment(db, session_id, current_user)
    return session_service.build_bill(session)