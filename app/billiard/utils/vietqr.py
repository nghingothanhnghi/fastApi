# app/billiard/utils/vietqr.py
# VietQR (NAPAS 247, EMVCo merchant-presented QR) payload builder. Pure functions,
# no network: the frontend renders `payload` as a QR code.
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from typing import Optional
from urllib.parse import quote

from app.billiard import config


def crc16_ccitt(data: str) -> str:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) as 4 uppercase hex chars."""
    crc = 0xFFFF
    for byte in data.encode("ascii"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def _tlv(tag: str, value: str) -> str:
    if len(value) > 99:
        raise ValueError(f"EMV field {tag} too long")
    return f"{tag}{len(value):02d}{value}"


def make_memo(session_id: int, line_id: int) -> str:
    """Short alphanumeric transfer content the cashier/bank feed can match, e.g. BIDA42L7."""
    return f"BIDA{session_id}L{line_id}"


def build_payload(bank_bin: str, account_no: str, amount: Decimal, memo: str) -> str:
    """Dynamic VietQR "transfer to account" payload with a fixed amount and memo."""
    whole = int(Decimal(amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if whole <= 0:
        raise ValueError("Amount must be greater than 0")
    if not memo.isalnum() or len(memo) > 25:
        raise ValueError("Memo must be alphanumeric and at most 25 characters")

    beneficiary = _tlv("00", bank_bin) + _tlv("01", account_no)
    merchant_info = (
        _tlv("00", "A000000727")            # NAPAS application id
        + _tlv("01", beneficiary)
        + _tlv("02", "QRIBFTTA")            # service: transfer to account
    )
    body = (
        _tlv("00", "01")                    # payload format
        + _tlv("01", "12")                  # 12 = dynamic QR (amount included)
        + _tlv("38", merchant_info)
        + _tlv("53", "704")                 # VND
        + _tlv("54", str(whole))
        + _tlv("58", "VN")
        + _tlv("62", _tlv("08", memo))
    )
    body += "6304"
    return body + crc16_ccitt(body)


def build_image_url(amount: Decimal, memo: str) -> Optional[str]:
    """Hosted QR image (img.vietqr.io) for UIs that cannot draw a QR themselves."""
    if not (config.BANK_CODE and config.BANK_ACCOUNT_NO):
        return None
    whole = int(Decimal(amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    url = (
        f"https://img.vietqr.io/image/{config.BANK_CODE}-{config.BANK_ACCOUNT_NO}-compact2.png"
        f"?amount={whole}&addInfo={quote(memo)}"
    )
    if config.BANK_ACCOUNT_NAME:
        url += f"&accountName={quote(config.BANK_ACCOUNT_NAME)}"
    return url


def build_transfer_instruction(amount: Decimal, memo: str, expires_at: Optional[datetime]) -> dict:
    """What the cashier screen / customer display needs to take a transfer."""
    payload = None
    if config.BANK_BIN and config.BANK_ACCOUNT_NO:
        payload = build_payload(config.BANK_BIN, config.BANK_ACCOUNT_NO, amount, memo)
    return {
        "bank_code": config.BANK_CODE or None,
        "account_no": config.BANK_ACCOUNT_NO or None,
        "account_name": config.BANK_ACCOUNT_NAME or None,
        "amount": amount,
        "memo": memo,
        "qr_payload": payload,
        "qr_image_url": build_image_url(amount, memo),
        "expires_at": expires_at,
    }
