# app/billiard/services/device_auth.py
# Device credentials are separate from user JWTs (spec section 35).
# The API key is a long random secret (e.g. secrets.token_urlsafe(32)), so a
# plain SHA-256 is sufficient; only the hash is stored in api_key_hash.
import hashlib
import hmac
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billiard.models import BilliardDevice, DeviceStatus


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def authenticate_device(db: Session, device_id: str, api_key: str) -> BilliardDevice:
    device = db.execute(
        select(BilliardDevice).where(BilliardDevice.device_id == device_id)
    ).scalar_one_or_none()

    # Always compare, even for an unknown device, so timing doesn't reveal which ids exist.
    expected = device.api_key_hash if device else hash_api_key("unknown-device")
    key_ok = hmac.compare_digest(hash_api_key(api_key or ""), expected)
    if device is None or not key_ok:
        raise HTTPException(401, "Invalid device credentials")

    device.last_seen = datetime.now(timezone.utc)
    device.status = DeviceStatus.ONLINE
    db.flush()
    return device