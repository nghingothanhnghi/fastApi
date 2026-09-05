# app/auth_provider/models/external_identity.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import relationship
from app.database import Base


class ExternalIdentity(Base):
    """Links a local User to one external OAuth account (1 user : N identities)."""
    __tablename__ = "external_identities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    provider = Column(String(30), nullable=False)          # "google" | "facebook"
    provider_user_id = Column(String(255), nullable=False)  # provider's stable "sub"/"id"
    email = Column(String(255), nullable=True)

    # Only store if you need to call the provider API later; otherwise drop these.
    access_token = Column(String, nullable=True)
    refresh_token = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="external_identities")

    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_provider_identity"),
    )