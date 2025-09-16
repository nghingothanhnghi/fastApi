import stripe
from app.payments.config import STRIPE_API_KEY
from typing import Dict, Any

stripe.api_key = STRIPE_API_KEY

class StripeProvider:
    def create_payment_intent(self, amount: float, currency: str = "usd", metadata: Dict[str, Any] = None):
        """
        Create a Stripe PaymentIntent and return client secret.
        """
        intent = stripe.PaymentIntent.create(
            amount=int(amount * 100),  # Stripe uses cents
            currency=currency,
            metadata=metadata or {},
        )
        return {
            "id": intent.id,
            "client_secret": intent.client_secret,
            "status": intent.status,
        }

    def retrieve_payment_intent(self, intent_id: str):
        """Retrieve an existing payment intent"""
        return stripe.PaymentIntent.retrieve(intent_id)

    def refund_payment(self, intent_id: str, amount: float = None):
        """Refund full or partial payment"""
        refund = stripe.Refund.create(
            payment_intent=intent_id,
            amount=int(amount * 100) if amount else None,
        )
        return refund

# ✅ Singleton instance
stripe_provider = StripeProvider()
