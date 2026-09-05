# app/auth_provider/providers/registry.py
from .google import google_provider
from .facebook import facebook_provider


class OAuthProviderRegistry:
    def __init__(self):
        self.providers = {
            "google": google_provider,
            "facebook": facebook_provider,
        }

    def get_provider(self, name: str) -> "OAuthProvider":
        provider = self.providers.get(name)
        if not provider:
            raise ValueError(f"Unsupported oauth provider: {name}")
        return provider


oauth_provider_registry = OAuthProviderRegistry()