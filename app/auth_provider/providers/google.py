# app/auth_provider/providers/google.py
import httpx
from urllib.parse import urlencode
from app.auth_provider.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from .base import OAuthProvider, OAuthUserInfo

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


class GoogleOAuthProvider(OAuthProvider):
    name = "google"

    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(TOKEN_URL, data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
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


google_provider = GoogleOAuthProvider()