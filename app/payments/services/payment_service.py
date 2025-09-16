# app/payments/services/payment_service.py
# PaymentService handles generic DB operations (CRUD), StripeService handles Stripe logic.
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.payments.models.payment import PaymentTransaction, PaymentStatus
from app.payments.schemas.payment import PaymentCreate, PaymentUpdate
from app.payments.utils.payment_query_utils import apply_payment_filters

class PaymentService:

    def create_payment(self, db: Session, payment_in: PaymentCreate) -> PaymentTransaction:
        try:
            payment = PaymentTransaction(**payment_in.dict())
            db.add(payment)
            db.commit()
            db.refresh(payment)
            return payment
        except SQLAlchemyError as e:
            db.rollback()
            raise e

    def get_payment(self, db: Session, payment_id: int) -> Optional[PaymentTransaction]:
        return db.query(PaymentTransaction).filter(PaymentTransaction.id == payment_id).first()


    def get_payments_by_user(
        self,
        db: Session,
        user_id: int,
        status: Optional[str] = None,
        provider: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[PaymentTransaction]:
        query = db.query(PaymentTransaction).filter(PaymentTransaction.user_id == user_id)
        query = apply_payment_filters(query, status, provider, start_date, end_date, limit, offset)
        return query.all()

    def get_payments_by_client_id(
        self,
        db: Session,
        client_id: str,
        status: Optional[str] = None,
        provider: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[PaymentTransaction]:
        query = db.query(PaymentTransaction).filter(PaymentTransaction.client_id == client_id)
        query = apply_payment_filters(query, status, provider, start_date, end_date, limit, offset)
        return query.all()

    def get_payment_by_reference(self, db: Session, reference_id: str) -> Optional[PaymentTransaction]:
        return db.query(PaymentTransaction).filter(PaymentTransaction.reference_id == reference_id).first()

    def update_payment_status(
        self, db: Session, payment_id: int, updates: PaymentUpdate
    ) -> Optional[PaymentTransaction]:
        payment = self.get_payment(db, payment_id)
        if not payment:
            return None
        try:
            for field, value in updates.dict(exclude_unset=True).items():
                setattr(payment, field, value)
            db.commit()
            db.refresh(payment)
            return payment
        except SQLAlchemyError as e:
            db.rollback()
            raise e

    def delete_payment(self, db: Session, payment_id: int) -> bool:
        payment = self.get_payment(db, payment_id)
        if not payment:
            return False
        try:
            db.delete(payment)
            db.commit()
            return True
        except SQLAlchemyError as e:
            db.rollback()
            raise e

# ✅ Export singleton instance
payment_service = PaymentService()
