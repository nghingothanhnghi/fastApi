# app/payments/routes/payment_router.py
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import get_db
from app.payments.schemas.payment import PaymentCreate, PaymentUpdate, PaymentOut
from app.payments.controllers import payment_controller

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/", response_model=PaymentOut)
def create_payment(payload: PaymentCreate, db: Session = Depends(get_db)):
    return payment_controller.create_payment_controller(db, payload)


@router.patch("/{payment_id}", response_model=PaymentOut)
def update_payment(payment_id: int, payload: PaymentUpdate, db: Session = Depends(get_db)):
    payment = payment_controller.update_payment_status_controller(db, payment_id, payload)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment transaction not found")
    return payment

@router.get("/client/{client_id}", response_model=List[PaymentOut])
def get_client_payments(
    client_id: str,
    status: Optional[str] = Query(None, description="Optional payment status filter"),
    start_date: Optional[datetime] = Query(None, description="Filter payments created after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter payments created before this date"),
    limit: Optional[int] = Query(None, description="Max number of results to return"),
    offset: Optional[int] = Query(None, description="Number of results to skip"),
    db: Session = Depends(get_db)
):
    return payment_controller.get_client_payments_controller(
        db, client_id, status, start_date, end_date
    )


@router.get("/user/{user_id}", response_model=List[PaymentOut])
def get_user_payments(
    user_id: int,
    status: Optional[str] = Query(None, description="Optional payment status filter"),
    start_date: Optional[datetime] = Query(None, description="Filter payments created after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter payments created before this date"),
    limit: Optional[int] = Query(None, description="Max number of results to return"),
    offset: Optional[int] = Query(None, description="Number of results to skip"),
    db: Session = Depends(get_db)
):
    return payment_controller.get_user_payments_controller(
        db, user_id, status, start_date, end_date
    )