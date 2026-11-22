# app/payments/utils/vietqr.py
# VietQR (NAPAS 247, EMVCo merchant-presented QR) payload builder. Pure functions,
# no network: the frontend renders `payload` as a QR code.
#
# CHANGED vs. the previous version: build_image_url and build_transfer_instruction take an
# optional `account` (a PaymentBankAccount row of the club). When it is None they fall back to the
# old config.BANK_* env values, so nothing breaks while clubs are being set up.
# crc16_ccitt, _tlv, make_memo and build_payload are unchanged.
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from typing import Optional
from urllib.parse import quote

from app.payments import config


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


def make_memo(order_id: int, line_id: int) -> str:
    """Short alphanumeric transfer content the cashier/bank feed can match, e.g. PAY42L7.

    The prefix is config.MEMO_PREFIX; the bank feed searches transfer content for the same pattern.
    """
    return f"{config.MEMO_PREFIX}{order_id}L{line_id}"


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


def _receiving_account(account=None) -> dict:
    """The account to show: the club's PaymentBankAccount if given, else the old env values."""
    if account is not None:
        return {
            "bank_bin": account.bank_bin,
            "bank_code": account.bank_code,
            "account_no": account.account_no,
            "account_name": account.account_name,
        }
    return {
        "bank_bin": config.BANK_BIN,
        "bank_code": config.BANK_CODE,
        "account_no": config.BANK_ACCOUNT_NO,
        "account_name": config.BANK_ACCOUNT_NAME,
    }


def build_image_url(amount: Decimal, memo: str, account=None) -> Optional[str]:
    """Hosted QR image (img.vietqr.io) for UIs that cannot draw a QR themselves."""
    acc = _receiving_account(account)
    bank = acc["bank_code"] or acc["bank_bin"]  # img.vietqr.io accepts a short code or a BIN
    if not (bank and acc["account_no"]):
        return None
    whole = int(Decimal(amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    url = (
        f"https://img.vietqr.io/image/{bank}-{acc['account_no']}-compact2.png"
        f"?amount={whole}&addInfo={quote(memo)}"
    )
    if acc["account_name"]:
        url += f"&accountName={quote(acc['account_name'])}"
    return url


def build_transfer_instruction(
    amount: Decimal, memo: str, expires_at: Optional[datetime], account=None
) -> dict:
    """What the cashier screen / customer display needs to take a transfer."""
    acc = _receiving_account(account)
    payload = None
    if acc["bank_bin"] and acc["account_no"]:
        payload = build_payload(acc["bank_bin"], acc["account_no"], amount, memo)
    return {
        "bank_code": acc["bank_code"] or None,
        "account_no": acc["account_no"] or None,
        "account_name": acc["account_name"] or None,
        "amount": amount,
        "memo": memo,
        "qr_payload": payload,
        "qr_image_url": build_image_url(amount, memo, account),
        "expires_at": expires_at,
    }
