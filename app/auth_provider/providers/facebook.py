# app/auth_provider/providers/facebook.py
import httpx
from urllib.parse import urlencode
from app.auth_provider.config import FACEBOOK_APP_ID, FACEBOOK_APP_SECRET
from .base import OAuthProvider, OAuthUserInfo

AUTH_URL = "https://www.facebook.com/v17.0/dialog/oauth"
TOKEN_URL = "https://graph.facebook.com/v17.0/oauth/access_token"
USERINFO_URL = "https://graph.facebook.com/v17.0/me"

FACEBOOK_USER_FIELDS = "id,email,first_name,last_name,picture.type(large)"


class FacebookOAuthProvider(OAuthProvider):
    name = "facebook"

    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": FACEBOOK_APP_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "public_profile,email",
            "state": state,
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(TOKEN_URL, params={
                "client_id": FACEBOOK_APP_ID,
                "client_secret": FACEBOOK_APP_SECRET,
                "code": code,
                "redirect_uri": redirect_uri,
            })
            resp.raise_for_status()
            return resp.json()

    async def fetch_user_info(self, token_data: dict) -> OAuthUserInfo:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                USERINFO_URL,
                params={"fields": FACEBOOK_USER_FIELDS},
                headers={"Authorization": f"Bearer {token_data['access_token']}"},
            )
            resp.raise_for_status()
            data = resp.json()

        picture_url = (
            data.get("picture", {}).get("data", {}).get("url")
            if data.get("picture") else None
        )

        return OAuthUserInfo(
            provider=self.name,
            provider_user_id=data["id"],
            email=data.get("email"),
            # Facebook only ever returns an email if it has already been
            # verified by the user, so treat presence of email as verified.
            email_verified=bool(data.get("email")),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            picture=picture_url,
        )


facebook_provider = FacebookOAuthProvider()