# app/payments/services/stripe_service.py
# StripeService handles Stripe-specific payment operations.

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.payments.models.payment import PaymentTransaction, PaymentStatus
from app.payments.providers.stripe_provider import stripe_provider
from app.payments.schemas.payment import StripePaymentResponse, PaymentOut

class StripeService:
    """Handles all Stripe-specific payment operations."""

    def create_payment(
        self,
        db: Session,
        user_id: int,
        client_id: str,
        amount: float,
        currency: str = "usd",
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> StripePaymentResponse:
        """Creates a Stripe PaymentIntent and logs it to DB."""
        intent = stripe_provider.create_payment_intent(amount, currency, extra_metadata)

        # Save to DB
        payment = PaymentTransaction(
            user_id=user_id,
            client_id=client_id,
            provider="stripe",
            amount=amount,
            currency=currency,
            status=PaymentStatus.PENDING,
            reference_id=intent["id"],
            extra_metadata=extra_metadata,
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)

        return StripePaymentResponse(
            payment=PaymentOut.model_validate(payment),
            stripe=intent,
        )

    def confirm_payment(self, db: Session, reference_id: str) -> Optional[PaymentTransaction]:
        """Retrieves Stripe PaymentIntent and updates status in DB."""
        payment = db.query(PaymentTransaction).filter(PaymentTransaction.reference_id == reference_id).first()
        if not payment:
            return None

        intent = stripe_provider.retrieve_payment_intent(reference_id)
        if intent.status == "succeeded":
            payment.status = PaymentStatus.COMPLETED
        elif intent.status == "requires_payment_method":
            payment.status = PaymentStatus.FAILED
        else:
            payment.status = PaymentStatus.PENDING

        db.commit()
        db.refresh(payment)
        return PaymentOut.model_validate(payment)

    def refund_payment(self, db: Session, reference_id: str, amount: float = None) -> Optional[PaymentTransaction]:
        """Refunds Stripe payment and updates status in DB."""
        payment = db.query(PaymentTransaction).filter(PaymentTransaction.reference_id == reference_id).first()
        if not payment:
            return None

        stripe_provider.refund_payment(reference_id, amount)
        payment.status = PaymentStatus.REFUNDED
        db.commit()
        db.refresh(payment)
        return PaymentOut.model_validate(payment)


# ✅ Export singleton instance
stripe_service = StripeService()
