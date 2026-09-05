# app/auth_provider/utils/provider_helpers.py
import re
import secrets
from sqlalchemy.orm import Session
from app.user.user import get_user_by_username


def generate_username_from_email(db: Session, email: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_]", "", email.split("@")[0]) or "user"
    candidate = base
    while get_user_by_username(db, candidate):
        candidate = f"{base}_{secrets.token_hex(2)}"
    return candidate