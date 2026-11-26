# app/billiard/routes/session_router.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.user.enums.role_enum import RoleEnum
from app.user.models.user import User
from app.user.utils.role_requirements import require_roles
from app.user.utils.token import get_current_user
from app.billiard.schemas.session import (
    AddItemResponse, AddSessionItemRequest, BillingReviewItem, BillingReviewRequest, BillResponse, CancelSessionRequest,
    DiscountRequest, ExtendSessionRequest, PayResponse, SessionItemResponse,
)
from app.billiard.services.payment_service import billiard_payment_service
from app.billiard.services.session_service import session_service
from app.payments.schemas.order import (
    CancelPaymentLineRequest, ConfirmTransferRequest, PayOrderRequest, PaymentEventResponse,
    VoidPaymentLineRequest,
)

router = APIRouter(prefix="/sessions", tags=["Billiard Sessions"])


@router.get("/billing-review", response_model=list[BillingReviewItem])
def list_billing_reviews(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Sessions that need a cashier decision before they can be paid. Declared before /{session_id}."""
    return session_service.list_billing_reviews(db, current_user)


@router.get("/{session_id}", response_model=BillResponse)
def get_bill(session_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Re-print a bill / receipt at any time (built from snapshots)."""
    return session_service.build_bill(session_service.get_session(db, session_id, current_user))


@router.post("/{session_id}/items", response_model=AddItemResponse, status_code=201)
def add_item(
    session_id: int, request: AddSessionItemRequest,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    lines = session_service.add_item_lines(
        db, session_id, request.product_id, request.quantity, request.variant_id, current_user
    )
    db.commit()
    views = [
        SessionItemResponse(
            id=i.id, product_id=i.product_id, variant_id=i.variant_id,
            product_name=i.product_name, quantity=i.quantity,
            unit_price=i.unit_price, total_price=i.total_price, from_package=i.from_package,
        ) for i in lines
    ]
    return AddItemResponse(**views[-1].model_dump(), lines=views)    # top level = paid line if any, as before


@router.post("/{session_id}/billing-review", response_model=BillResponse)
def resolve_billing_review(
    session_id: int, request: BillingReviewRequest,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Resolve a flagged session: assign a valid package, or confirm normal pricing (note required).
    The decision is recorded (who, when, what, note) and unblocks payment."""
    session = session_service.resolve_billing_review(
        db, session_id, request.action, request.package_id, request.note, current_user
    )
    db.commit()
    db.refresh(session)
    return session_service.build_bill(session)


@router.post("/{session_id}/stop", response_model=BillResponse)
def stop_session(session_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    session = session_service.stop_session(db, session_id, current_user)
    db.commit()
    db.refresh(session)
    return session_service.build_bill(session)


@router.post("/{session_id}/extend", response_model=BillResponse)
def extend_session(
    session_id: int, request: ExtendSessionRequest,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Add `minutes` to the countdown (ends_at) of an ACTIVE session. Billing is not changed."""
    session = session_service.extend_session(db, session_id, request.minutes, current_user)
    db.commit()
    db.refresh(session)
    return session_service.build_bill(session)


@router.post("/{session_id}/discount", response_model=BillResponse)
def set_discount(
    session_id: int, request: DiscountRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MANAGER)),
):
    """Manager only. Fixed amount or percent off (table fee + products); amount 0 removes it.
    `409` once a payment was started, because the payment total is then fixed."""
    session = session_service.set_discount(
        db, session_id, request.amount, request.percent, request.reason, current_user
    )
    db.commit()
    db.refresh(session)
    return session_service.build_bill(session)


@router.post("/{session_id}/cancel", response_model=BillResponse)
def cancel_session(
    session_id: int, request: CancelSessionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MANAGER)),
):
    """Manager only. Cancel an ACTIVE session opened by mistake: no bill, table freed, reason audited."""
    session = session_service.cancel_session(db, session_id, request.reason, current_user)
    db.commit()
    db.refresh(session)
    return session_service.build_bill(session)


@router.post("/{session_id}/pay", response_model=PayResponse)
def pay_session(
    session_id: int, request: PayOrderRequest,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    session, gateway = billiard_payment_service.pay_session(db, session_id, request, current_user)
    return {**session_service.build_bill(session), "gateway": gateway}


@router.post("/{session_id}/pay/confirm", response_model=BillResponse)
def confirm_payment(session_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Settle a gateway (Stripe) payment after the customer completes it."""
    session = billiard_payment_service.confirm_payment(db, session_id, current_user)
    return session_service.build_bill(session)


@router.post("/{session_id}/pay/lines/{line_id}/confirm", response_model=BillResponse)
def confirm_transfer_line(
    session_id: int, line_id: int, request: ConfirmTransferRequest | None = None,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Cashier confirms a bank transfer line was received."""
    session = billiard_payment_service.confirm_transfer(
        db, session_id, line_id, current_user, request.note if request else None
    )
    return session_service.build_bill(session)


@router.post("/{session_id}/pay/lines/{line_id}/cancel", response_model=BillResponse)
def cancel_payment_line(
    session_id: int, line_id: int, request: CancelPaymentLineRequest | None = None,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Void a pending line (e.g. the transfer never came); the balance can then be paid another way."""
    session = billiard_payment_service.cancel_line(
        db, session_id, line_id, current_user, request.reason if request else None
    )
    return session_service.build_bill(session)


@router.post("/{session_id}/pay/lines/{line_id}/void", response_model=BillResponse)
def void_payment_line(
    session_id: int, line_id: int, request: VoidPaymentLineRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MANAGER)),
):
    """Manager only. Reverse a completed payment line; a reason is required and audited."""
    session = billiard_payment_service.void_line(db, session_id, line_id, current_user, request.reason)
    return session_service.build_bill(session)


@router.get("/{session_id}/pay/events", response_model=list[PaymentEventResponse])
def payment_events(session_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Audit trail of every payment action on this bill."""
    return billiard_payment_service.list_events(db, session_id, current_user)
