# app/payments/routes/order_router.py  (HTTP only; rules live in order_service)
# Generic payment API for any business that registered a PayableAdapter. A business module can
# also expose its own friendlier URLs (billiard keeps /sessions/{id}/pay) and delegate here.
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.payments.schemas.order import (
    CancelPaymentLineRequest, ConfirmTransferRequest, OrderResponse, PayOrderRequest,
    PayOrderResponse, PaymentEventResponse, VoidPaymentLineRequest,
)
from app.payments.services.order_service import payment_order_service
from app.user.enums.role_enum import RoleEnum
from app.user.models.user import User
from app.user.utils.role_requirements import require_roles
from app.user.utils.token import get_current_user

router = APIRouter(prefix="/payments/orders", tags=["Payments - Orders"])


def _view(db: Session, source_type: str, source_id: str, user: User) -> dict:
    return payment_order_service.get_view(db, source_type, source_id, user)


@router.get("/{source_type}/{source_id}", response_model=OrderResponse)
def get_order(
    source_type: str, source_id: str,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """What is due, what was paid and every payment line for a business object."""
    return _view(db, source_type, source_id, current_user)


@router.post("/{source_type}/{source_id}/pay", response_model=PayOrderResponse)
def pay_order(
    source_type: str, source_id: str, request: PayOrderRequest,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Pay in one go or split the bill. The amount always comes from the business, never the client."""
    _, gateway = payment_order_service.pay(db, source_type, source_id, request, current_user)
    return {**_view(db, source_type, source_id, current_user), "gateway": gateway}


@router.post("/{source_type}/{source_id}/pay/confirm", response_model=OrderResponse)
def confirm_gateway_payment(
    source_type: str, source_id: str,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Settle a gateway (Stripe) payment after the customer completes it."""
    payment_order_service.confirm_gateway(db, source_type, source_id, current_user)
    return _view(db, source_type, source_id, current_user)


@router.post("/{source_type}/{source_id}/lines/{line_id}/confirm", response_model=OrderResponse)
def confirm_transfer_line(
    source_type: str, source_id: str, line_id: int, request: ConfirmTransferRequest | None = None,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Cashier confirms a bank transfer line was received."""
    payment_order_service.confirm_transfer(
        db, source_type, source_id, line_id, current_user, request.note if request else None
    )
    return _view(db, source_type, source_id, current_user)


@router.post("/{source_type}/{source_id}/lines/{line_id}/cancel", response_model=OrderResponse)
def cancel_payment_line(
    source_type: str, source_id: str, line_id: int, request: CancelPaymentLineRequest | None = None,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Void a pending line (e.g. the transfer never came); the balance can then be paid another way."""
    payment_order_service.cancel_line(
        db, source_type, source_id, line_id, current_user, request.reason if request else None
    )
    return _view(db, source_type, source_id, current_user)


@router.post("/{source_type}/{source_id}/lines/{line_id}/void", response_model=OrderResponse)
def void_payment_line(
    source_type: str, source_id: str, line_id: int, request: VoidPaymentLineRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MANAGER)),
):
    """Manager only. Reverse a completed payment line; a reason is required and audited."""
    payment_order_service.void_line(db, source_type, source_id, line_id, current_user, request.reason)
    return _view(db, source_type, source_id, current_user)


@router.get("/{source_type}/{source_id}/events", response_model=list[PaymentEventResponse])
def payment_events(
    source_type: str, source_id: str,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Audit trail of every payment action on this order."""
    return payment_order_service.list_events(db, source_type, source_id, current_user)
