from uuid import uuid4
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.payments.models.payment import PaymentTransaction, PaymentStatus
from app.payments.schemas.payment import PaymentOut

class ManualPaymentService:
    """Handles manual/offline payments (e.g. cash, bank transfer)."""

    def create_payment(
        self,
        db: Session,
        user_id: int,
        client_id: str,
        amount: float,
        currency: str = "usd",
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Creates a manual payment record directly in DB."""

        # ✅ Generate always-unique reference_id
        reference_id = f"manual-{user_id}-{client_id}-{uuid4().hex[:8]}"
        payment = PaymentTransaction(
            user_id=user_id,
            client_id=client_id,
            provider="manual",
            amount=amount,
            currency=currency,
            status=PaymentStatus.PENDING,  # Could also be COMPLETED if you want to mark it as paid immediately
            reference_id=reference_id,
            extra_metadata=extra_metadata,
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)

        return PaymentOut.model_validate(payment)

    def confirm_payment(self, db: Session, reference_id: str):
        """Marks manual payment as completed."""
        payment = db.query(PaymentTransaction).filter(PaymentTransaction.reference_id == reference_id).first()
        if not payment:
            return None
        payment.status = PaymentStatus.COMPLETED
        db.commit()
        db.refresh(payment)
        return PaymentOut.model_validate(payment)

    def refund_payment(self, db: Session, reference_id: str):
        """Marks manual payment as refunded (no external API call)."""
        payment = db.query(PaymentTransaction).filter(PaymentTransaction.reference_id == reference_id).first()
        if not payment:
            return None
        payment.status = PaymentStatus.REFUNDED
        db.commit()
        db.refresh(payment)
        return PaymentOut.model_validate(payment)


# ✅ Singleton instance
manual_payment_service = ManualPaymentService()
