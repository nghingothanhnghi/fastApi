import os
from dotenv import load_dotenv

load_dotenv()


def _env(*names: str, default: str = "") -> str:
    """First variable that is set wins. Lets the generic PAYMENT_* names replace the older
    BILLIARD_* ones without breaking deployments that still use them."""
    for name in names:
        value = os.getenv(name)
        if value is not None:
            return value
    return default


def _flag(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes")


# --- Stripe -------------------------------------------------------------------
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# --- Payment methods ------------------------------------------------------------
# API payment method -> provider key in payment_provider_registry
PAYMENT_METHODS = {
    "cash": "manual",
    "bank_transfer": "manual",
    "stripe": "stripe",
}

# Max number of lines when splitting one bill across several payments.
MAX_PAYMENT_LINES = 6

# --- Bank transfer (VietQR) -----------------------------------------------------
# A transfer line stays "pending" until the cashier (or the bank feed) confirms the money
# arrived. Set to false to treat a transfer as paid immediately, like cash.
BANK_TRANSFER_REQUIRES_CONFIRMATION = _flag(_env(
    "PAYMENT_BANK_TRANSFER_REQUIRES_CONFIRMATION", "BILLIARD_BANK_TRANSFER_REQUIRES_CONFIRMATION",
    default="true",
))
TRANSFER_EXPIRE_MINUTES = int(_env("PAYMENT_TRANSFER_EXPIRE_MINUTES", "BILLIARD_TRANSFER_EXPIRE_MINUTES", default="15"))
# Prefix of the transfer content that identifies a payment line, e.g. PAY12L34. Letters/digits only.
# If you use SePay's "payment code structure", set the same prefix there.
MEMO_PREFIX = _env("PAYMENT_MEMO_PREFIX", default="PAY").strip().upper() or "PAY"

# Receiving account. Without BIN + account number no QR is generated (a transfer line still
# works, the cashier just confirms it manually).
BANK_BIN = _env("PAYMENT_BANK_BIN", "BILLIARD_BANK_BIN")                       # NAPAS bank BIN, e.g. 970436
BANK_CODE = _env("PAYMENT_BANK_CODE", "BILLIARD_BANK_CODE")                    # short code for the QR image URL, e.g. VCB
BANK_ACCOUNT_NO = _env("PAYMENT_BANK_ACCOUNT_NO", "BILLIARD_BANK_ACCOUNT_NO")
BANK_ACCOUNT_NAME = _env("PAYMENT_BANK_ACCOUNT_NAME", "BILLIARD_BANK_ACCOUNT_NAME")

# --- Cash drawer ------------------------------------------------------------------
# When true, taking a payment is refused until a cashier has opened a shift.
REQUIRE_OPEN_SHIFT = _flag(_env("PAYMENT_REQUIRE_OPEN_SHIFT", "BILLIARD_REQUIRE_OPEN_SHIFT", default="false"))

# --- SePay bank feed ----------------------------------------------------------------
# https://developer.sepay.vn/en/sepay-webhooks : SePay posts every incoming transfer to
# POST /payments/bank-feed/sepay. Set ONE of these; the endpoint is disabled (503) when neither is set.
#   SECRET  -> HMAC-SHA256 (X-SePay-Signature / X-SePay-Timestamp), preferred
#   API_KEY -> "Authorization: Apikey <key>"
SEPAY_WEBHOOK_SECRET = os.getenv("SEPAY_WEBHOOK_SECRET", "")
SEPAY_API_KEY = os.getenv("SEPAY_API_KEY", "")
SEPAY_TIMESTAMP_TOLERANCE_SECONDS = int(os.getenv("SEPAY_TIMESTAMP_TOLERANCE_SECONDS", "300"))
