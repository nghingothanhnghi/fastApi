# app/auth_provider/utils/oauth_state.py
from datetime import datetime, timedelta
from jose import jwt, JWTError
from app.user.utils.token import SECRET_KEY, ALGORITHM  # reuse, don't duplicate


def create_state_token(redirect_after: str | None = None, ttl_minutes: int = 10) -> str:
    payload = {
        "purpose": "oauth_state",
        "redirect_after": redirect_after,
        "exp": datetime.utcnow() + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_state_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise ValueError("Invalid or expired OAuth state")
    if payload.get("purpose") != "oauth_state":
        raise ValueError("Invalid OAuth state payload")
    return payload