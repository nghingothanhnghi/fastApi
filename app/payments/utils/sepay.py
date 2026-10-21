# app/payments/utils/sepay.py
# Request authentication for SePay webhooks. Pure functions (no framework, no DB).
# Spec: https://developer.sepay.vn/en/sepay-webhooks/xac-thuc
#   HMAC-SHA256: X-SePay-Signature = "sha256=" + hex(HMAC(secret, f"{timestamp}.{raw_body}"))
#                X-SePay-Timestamp = unix seconds; reject if more than 5 minutes off
#   API key:     Authorization: Apikey <key>
import hashlib
import hmac
import time
from typing import Mapping, Optional


class SepayNotConfigured(Exception):
    """Neither a webhook secret nor an API key is set: the endpoint must stay closed."""


class SepayAuthError(Exception):
    """The request does not carry valid credentials."""


def _eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def verify_request(
    headers: Mapping[str, str],
    raw_body: bytes,
    *,
    secret: str,
    api_key: str,
    tolerance_seconds: int = 300,
    now: Optional[float] = None,
) -> str:
    """Return the method that verified ("hmac" or "api_key"), or raise.

    A configured secret wins: once HMAC is on, an API-key-only request is rejected.
    """
    h = {k.lower(): v for k, v in headers.items()}

    if secret:
        signature, timestamp = h.get("x-sepay-signature", ""), h.get("x-sepay-timestamp", "")
        if not signature or not timestamp:
            raise SepayAuthError("Missing signature headers")
        try:
            ts = int(timestamp)
        except ValueError:
            raise SepayAuthError("Invalid timestamp")
        if abs((now if now is not None else time.time()) - ts) > tolerance_seconds:
            raise SepayAuthError("Timestamp outside the allowed window")
        expected = "sha256=" + hmac.new(
            secret.encode("utf-8"), f"{timestamp}.".encode("utf-8") + raw_body, hashlib.sha256
        ).hexdigest()
        if not _eq(expected, signature):
            raise SepayAuthError("Invalid signature")
        return "hmac"

    if api_key:
        auth = h.get("authorization", "")
        if not auth.startswith("Apikey ") or not _eq(api_key, auth[len("Apikey "):]):
            raise SepayAuthError("Invalid API key")
        return "api_key"

    raise SepayNotConfigured()
