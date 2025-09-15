# app/payments/controllers/payment_controller.py
from sqlalchemy.orm import Session
from datetime import datetime
from app.payments.services.payment_service import payment_service
from app.payments.schemas.payment import PaymentCreate, PaymentUpdate


def create_payment_controller(db: Session, payload: PaymentCreate):
    return payment_service.create_payment(db, payload)


def update_payment_status_controller(db: Session, payment_id: int, payload: PaymentUpdate):
    return payment_service.update_payment_status(db, payment_id, payload)


def get_client_payments_controller(
    db: Session,
    client_id: str,
    status: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int | None = None,
    offset: int | None = None,
):
    return payment_service.get_payments_by_client_id(
        db,
        client_id=client_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


def get_user_payments_controller(
    db: Session,
    user_id: int,
    status: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int | None = None,
    offset: int | None = None,
):
    return payment_service.get_payments_by_user(
        db,
        user_id=user_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
