# app/auth_provider/services/identity_service.py
from typing import Optional
from sqlalchemy.orm import Session
from app.auth_provider.models.external_identity import ExternalIdentity


class IdentityService:
    def get_by_provider(self, db: Session, provider: str, provider_user_id: str) -> Optional[ExternalIdentity]:
        return db.query(ExternalIdentity).filter(
            ExternalIdentity.provider == provider,
            ExternalIdentity.provider_user_id == provider_user_id,
        ).first()

    def link(self, db: Session, user_id: int, provider: str, provider_user_id: str,
              email: Optional[str], access_token: Optional[str] = None,
              refresh_token: Optional[str] = None) -> ExternalIdentity:
        identity = ExternalIdentity(
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            email=email,
            access_token=access_token,
            refresh_token=refresh_token,
        )
        db.add(identity)
        db.commit()
        db.refresh(identity)
        return identity


identity_service = IdentityService()