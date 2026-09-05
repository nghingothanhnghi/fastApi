# app/auth_provider/services/oauth_service.py
import secrets
from sqlalchemy.orm import Session

from app.user import user as crud_user
from app.user.models.user import User
from app.user.schemas.user import UserCreate
from app.user.utils.token import create_access_token
from app.auth_provider.providers.base import OAuthUserInfo
from app.auth_provider.services.identity_service import identity_service
from app.auth_provider.utils.provider_helpers import generate_username_from_email


class OAuthService:

    def login_or_register(self, db: Session, info: OAuthUserInfo, token_data: dict) -> dict:
        # 1) Already linked before -> straight login
        identity = identity_service.get_by_provider(db, info.provider, info.provider_user_id)
        if identity:
            user = db.query(User).filter(User.id == identity.user_id).first()
            return self._issue_token(user)

        # 2) Not linked yet, but an account with this email already exists -> link it
        user = None
        if info.email:
            user = crud_user.get_user_by_email(db, info.email)

        # 3) Brand-new person -> create via the SAME path normal signup uses
        if not user:
            user = self._create_user_from_oauth(db, info)

        identity_service.link(
            db, user_id=user.id, provider=info.provider,
            provider_user_id=info.provider_user_id, email=info.email,
            access_token=token_data.get("access_token"),
            refresh_token=token_data.get("refresh_token"),
        )
        return self._issue_token(user)

    def _create_user_from_oauth(self, db: Session, info: OAuthUserInfo) -> User:
        # OAuth users don't set a password themselves; generate an unusable
        # random one so UserCreate's required `password` field is satisfied
        # and the normal /password/forgot flow still works if they ever want one.
        random_password = secrets.token_urlsafe(24)
        username = generate_username_from_email(db, info.email or f"{info.provider}_{info.provider_user_id}")

        user_in = UserCreate(
            username=username,
            email=info.email or f"{info.provider}_{info.provider_user_id}@no-email.local",
            password=random_password,
            first_name=info.first_name,
            last_name=info.last_name,
            image_url=info.picture,
        )
        # current_user=None -> public self-signup path in crud_user.create_user,
        # which already assigns the default "user" role and a fresh client_id.
        return crud_user.create_user(db, user_in, current_user=None)

    def _issue_token(self, user: User) -> dict:
        access_token = create_access_token(data={"sub": user.username})
        return {"access_token": access_token, "token_type": "bearer"}


oauth_service = OAuthService()