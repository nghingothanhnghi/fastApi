# app/auth_provider/providers/base.py
from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel


class OAuthUserInfo(BaseModel):
    provider: str
    provider_user_id: str
    email: Optional[str] = None
    email_verified: bool = False
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    picture: Optional[str] = None


class OAuthProvider(ABC):
    name: str

    @abstractmethod
    def get_authorization_url(self, state: str, redirect_uri: str) -> str: ...

    @abstractmethod
    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> dict: ...

    @abstractmethod
    async def fetch_user_info(self, token_data: dict) -> OAuthUserInfo: ...