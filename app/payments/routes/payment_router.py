# app/payments/routes/payment_router.py
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import get_db
from app.payments.schemas.payment import PaymentCreate, PaymentUpdate, PaymentOut, StripePaymentCreate, StripePaymentResponse, PaginatedPayments
from app.payments.controllers import payment_controller
from app.user.utils.token import get_current_user
from app.user.utils.role_requirements import require_roles
from app.user.enums.role_enum import RoleEnum

router = APIRouter(prefix="/payments", tags=["Payments"])

@router.get("/", response_model=PaginatedPayments)
def get_all_payments(
    status: Optional[str] = Query(None, description="Optional payment status filter"),
    provider: Optional[str] = Query(None, description="Optional payment provider filter (e.g. stripe, paypal)"),
    start_date: Optional[datetime] = Query(None, description="Filter payments created after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter payments created before this date"),
    limit: Optional[int] = Query(100, description="Max number of results to return"),
    offset: Optional[int] = Query(0, description="Number of results to skip"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Return all payments if SUPER_ADMIN, otherwise return payments filtered by user/client.
    """
    is_super_admin = any(role.name == RoleEnum.SUPER_ADMIN for role in current_user.roles)

    if is_super_admin:
        return payment_controller.get_all_payments(
            db=db,
            status=status,
            provider=provider,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )
    elif current_user.client_id:
        payments = payment_controller.get_client_payments(
            db=db,
            client_id=current_user.client_id,
            status=status,
            provider=provider,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )
        return {"results": payments, "total": len(payments)}
    else:
        payments = payment_controller.get_user_payments(
            db=db,
            user_id=current_user.id,
            status=status,
            provider=provider,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )
        return {"results": payments, "total": len(payments)}
    

@router.post("/", response_model=PaymentOut)
def create_payment(payload: PaymentCreate, db: Session = Depends(get_db)):
    return payment_controller.create_payment(db=db, payload=payload)


@router.patch("/{payment_id}", response_model=PaymentOut)
def update_payment(payment_id: int, payload: PaymentUpdate, db: Session = Depends(get_db)):
    payment = payment_controller.update_payment_status(db=db, payment_id=payment_id, payload=payload)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment transaction not found")
    return payment

@router.get("/client/{client_id}", response_model=PaginatedPayments)
def get_client_payments(
    client_id: str,
    status: Optional[str] = Query(None, description="Optional payment status filter"),
    provider: str | None = Query(None, description="Optional payment provider filter (e.g. stripe, paypal)"),
    start_date: Optional[datetime] = Query(None, description="Filter payments created after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter payments created before this date"),
    limit: Optional[int] = Query(None, description="Max number of results to return"),
    offset: Optional[int] = Query(None, description="Number of results to skip"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    is_super_admin = any(role.name == RoleEnum.SUPER_ADMIN for role in current_user.roles)

    if not is_super_admin and current_user.client_id != client_id:
        # Only SUPER_ADMIN can access other clients
        raise HTTPException(status_code=403, detail="Not authorized to view this client's payments")

    payments = payment_controller.get_client_payments(
        db=db,
        client_id=client_id,
        status=status,
        provider=provider,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return {"results": payments, "total": len(payments)}

@router.get("/user/{user_id}", response_model=PaginatedPayments)
def get_user_payments(
    user_id: int,
    status: Optional[str] = Query(None, description="Optional payment status filter"),
    provider: str | None = Query(None, description="Optional payment provider filter (e.g. stripe, paypal)"),
    start_date: Optional[datetime] = Query(None, description="Filter payments created after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter payments created before this date"),
    limit: Optional[int] = Query(None, description="Max number of results to return"),
    offset: Optional[int] = Query(None, description="Number of results to skip"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    is_super_admin = any(role.name == RoleEnum.SUPER_ADMIN for role in current_user.roles)

    if not is_super_admin and current_user.id != user_id:
        # Only SUPER_ADMIN or the user themselves can view their payments
        raise HTTPException(status_code=403, detail="Not authorized to view this user's payments")

    payments = payment_controller.get_user_payments(
        db=db,
        user_id=user_id,
        status=status,
        provider=provider,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return {"results": payments, "total": len(payments)}


# ─────────────────────────────
# 🟦 Stripe-specific Endpoints
# ─────────────────────────────

stripe_router = APIRouter(prefix="/stripe", tags=["Payments - Stripe"])

@stripe_router.post("/create", response_model=StripePaymentResponse)
def create_stripe_payment(
    payload: StripePaymentCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleEnum.ADMIN, RoleEnum.SUPER_ADMIN))
):
    """Creates a Stripe PaymentIntent and stores transaction in DB."""
    return payment_controller.create_stripe_payment(db=db, payload=payload)


@stripe_router.post("/confirm/{reference_id}", response_model=PaymentOut)
def confirm_stripe_payment(
    reference_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleEnum.ADMIN, RoleEnum.SUPER_ADMIN))
):
    """Confirms Stripe payment by retrieving PaymentIntent status."""
    payment = payment_controller.confirm_stripe_payment(db=db, reference_id=reference_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Stripe payment not found")
    return payment


@stripe_router.post("/refund/{reference_id}", response_model=PaymentOut)
def refund_stripe_payment(
    reference_id: str,
    amount: Optional[float] = Query(None, description="Optional partial refund amount"),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleEnum.ADMIN, RoleEnum.SUPER_ADMIN))
):
    """Refunds a Stripe payment and updates transaction status in DB."""
    payment = payment_controller.refund_stripe_payment(db=db, reference_id=reference_id, amount=amount)
    if not payment:
        raise HTTPException(status_code=404, detail="Stripe payment not found")
    return payment


# ─────────────────────────────
# Include stripe router under /payments
# ─────────────────────────────
router.include_router(stripe_router)