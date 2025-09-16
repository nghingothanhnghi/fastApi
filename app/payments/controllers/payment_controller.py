# app/payments/controllers/payment_controller.py
from sqlalchemy.orm import Session
from datetime import datetime
from app.payments.services.payment_service import payment_service
from app.payments.schemas.payment import PaymentCreate, PaymentUpdate, StripePaymentCreate, StripePaymentResponse, PaymentOut
from typing import Dict, Any
from app.payments.services.stripe_service import stripe_service

def create_payment(db: Session, payload: PaymentCreate):
    return payment_service.create_payment(db, payload)


def update_payment_status(db: Session, payment_id: int, payload: PaymentUpdate):
    return payment_service.update_payment_status(db, payment_id, payload)


def get_client_payments(
    db: Session,
    client_id: str,
    status: str | None = None,
    provider: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int | None = None,
    offset: int | None = None,
):
    return payment_service.get_payments_by_client_id(
        db,
        client_id=client_id,
        status=status,
        provider=provider,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


def get_user_payments(
    db: Session,
    user_id: int,
    status: str | None = None,
    provider: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int | None = None,
    offset: int | None = None,
):
    return payment_service.get_payments_by_user(
        db,
        user_id=user_id,
        status=status,
        provider=provider,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )

def create_stripe_payment(db: Session, payload: StripePaymentCreate) -> StripePaymentResponse:
    return stripe_service.create_payment(
        db,
        user_id=payload.user_id,
        client_id=payload.client_id,
        amount=payload.amount,
        currency=payload.currency,
        extra_metadata=payload.extra_metadata,
    )


def confirm_stripe_payment(db: Session, reference_id: str) -> PaymentOut | None:
    return stripe_service.confirm_payment(db, reference_id)


def refund_stripe_payment(db: Session, reference_id: str, amount: float = None) -> PaymentOut | None:
    return stripe_service.refund_payment(db, reference_id, amount)
