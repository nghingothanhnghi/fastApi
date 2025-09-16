from app.payments.services.stripe_service import stripe_service


class PaymentProviderRegistry:
    """Registry for available payment provider services."""

    def __init__(self):
        # Register available providers here
        self.providers = {
            "stripe": stripe_service,
            # "paypal": paypal_service (future)
        }

    def get_provider(self, provider: str):
        """Return the service for the given provider."""
        service = self.providers.get(provider)
        if not service:
            raise ValueError(f"Unsupported payment provider: {provider}")
        return service


# ✅ Singleton instance
payment_provider_registry = PaymentProviderRegistry()
