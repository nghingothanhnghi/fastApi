# app/auth_provider/providers/google.py
import httpx
from urllib.parse import urlencode
from app.auth_provider.config import FACEBOOK_APP_ID, FACEBOOK_APP_SECRET
from .base import OAuthProvider, OAuthUserInfo

AUTH_URL = "https://www.facebook.com/v17.0/dialog/oauth"
TOKEN_URL = "https://graph.facebook.com/v17.0/oauth/access_token"
USERINFO_URL = "https://graph.facebook.com/v17.0/me"


class GoogleOAuthProvider(OAuthProvider):
    name = "google"

    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": FACEBOOK_APP_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "public_profile email",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(TOKEN_URL, data={
                "client_id": FACEBOOK_APP_ID,
                "client_secret": FACEBOOK_APP_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            })
            resp.raise_for_status()
            return resp.json()

    async def fetch_user_info(self, token_data: dict) -> OAuthUserInfo:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                USERINFO_URL,
                headers={"Authorization": f"Bearer {token_data['access_token']}"},
            )
            resp.raise_for_status()
            data = resp.json()

        return OAuthUserInfo(
            provider=self.name,
            provider_user_id=data["sub"],
            email=data.get("email"),
            email_verified=data.get("email_verified", False),
            first_name=data.get("given_name"),
            last_name=data.get("family_name"),
            picture=data.get("picture"),
        )


facebook_provider = GoogleOAuthProvider()