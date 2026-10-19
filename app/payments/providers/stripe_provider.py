import stripe
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Optional, Union

from app.payments.config import STRIPE_API_KEY

stripe.api_key = STRIPE_API_KEY

# Currencies Stripe treats as zero-decimal: the amount is already in the
# smallest unit, so it must NOT be multiplied by 100 (e.g. 310000 VND -> 310000).
# https://docs.stripe.com/currencies#zero-decimal
ZERO_DECIMAL_CURRENCIES = frozenset({
    "bif", "clp", "djf", "gnf", "jpy", "kmf", "krw", "mga",
    "pyg", "rwf", "ugx", "vnd", "vuv", "xaf", "xof", "xpf",
})

# Three-decimal currencies: multiply by 1000. Stripe requires the last digit
# to be 0 (i.e. the amount must be rounded to 2 decimals' precision).
# https://docs.stripe.com/currencies#three-decimal
THREE_DECIMAL_CURRENCIES = frozenset({"bhd", "jod", "kwd", "omr", "tnd"})


def normalize_currency(currency: Optional[str], default: str = "usd") -> str:
    """Stripe requires lowercase three-letter ISO currency codes."""
    code = (currency or default).strip().lower()
    if len(code) != 3 or not code.isalpha():
        raise ValueError(f"Invalid currency code: {currency!r}")
    return code


def to_stripe_amount(amount: Union[int, float, str, Decimal], currency: str) -> int:
    """
    Convert a human-readable amount into the integer smallest-unit amount Stripe expects.

    - zero-decimal (vnd, jpy, krw, ...): 310000 -> 310000
    - two-decimal  (usd, eur, ...):      19.99  -> 1999
    - three-decimal (kwd, bhd, ...):     1.234  -> 1230 (last digit must be 0)

    Uses Decimal with ROUND_HALF_UP to avoid float errors like int(19.99 * 100) == 1998.
    """
    code = normalize_currency(currency)
    value = Decimal(str(amount))
    if not value.is_finite() or value <= 0:
        raise ValueError("Amount must be greater than 0")

    if code in ZERO_DECIMAL_CURRENCIES:
        return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if code in THREE_DECIMAL_CURRENCIES:
        cents = int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return cents * 10
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class StripeProvider:
    def create_payment_intent(self, amount: float, currency: str = "usd", metadata: Dict[str, Any] = None):
        """
        Create a Stripe PaymentIntent and return client secret.
        """
        currency = normalize_currency(currency)
        intent = stripe.PaymentIntent.create(
            amount=to_stripe_amount(amount, currency),
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

    def refund_payment(self, intent_id: str, amount: float = None, currency: str = "usd"):
        """Refund full (amount=None) or partial payment. `currency` must match the original charge."""
        params: Dict[str, Any] = {"payment_intent": intent_id}
        if amount is not None:
            params["amount"] = to_stripe_amount(amount, currency)
        return stripe.Refund.create(**params)

# ✅ Singleton instance
stripe_provider = StripeProvider()
