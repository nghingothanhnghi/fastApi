# app/payments/utils/vietqr_parser.py
"""Parse a VietQR / NAPAS 247 payload (the text inside a bank QR image).

Only account-based transfers (QRIBFTTA) are accepted. Card QRs (QRIBFTTC) and
anything malformed raise ValueError.
"""
from dataclasses import dataclass

NAPAS_GUID = "A000000727"


def _crc16_ccitt(text: str) -> str:
    """CRC16-CCITT (poly 0x1021, init 0xFFFF), uppercase hex. Same as vietqr.crc16_ccitt."""
    crc = 0xFFFF
    for b in text.encode("ascii", errors="replace"):
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


@dataclass(frozen=True)
class ParsedBankQr:
    bank_bin: str
    account_no: str
    amount: int | None = None
    memo: str | None = None


def _tlv(text: str) -> dict[str, str]:
    """Parse a flat TLV string into {tag: value}. Raises ValueError if malformed."""
    out: dict[str, str] = {}
    i, n = 0, len(text)
    while i < n:
        if i + 4 > n:
            raise ValueError("Malformed QR: truncated field")
        tag, length = text[i:i + 2], text[i + 2:i + 4]
        if not length.isdigit():
            raise ValueError("Malformed QR: bad length")
        end = i + 4 + int(length)
        if end > n:
            raise ValueError("Malformed QR: field overruns payload")
        out[tag] = text[i + 4:end]
        i = end
    return out


def parse_vietqr(payload: str) -> ParsedBankQr:
    text = (payload or "").strip()
    if len(text) < 20 or text[-8:-4] != "6304":
        raise ValueError("Not a VietQR payload")
    if _crc16_ccitt(text[:-4]) != text[-4:].upper():
        raise ValueError("QR checksum is invalid")

    root = _tlv(text)
    t38 = root.get("38")
    if not t38:
        raise ValueError("Not a bank-transfer QR (missing tag 38)")
    sub = _tlv(t38)
    if sub.get("00") != NAPAS_GUID:
        raise ValueError("Not a NAPAS 247 QR")
    service = sub.get("02")
    if service == "QRIBFTTC":
        raise ValueError("This is a card QR, which is not supported; use an account QR")
    if service != "QRIBFTTA":
        raise ValueError("Unsupported QR service")

    bene = _tlv(sub.get("01", ""))
    bank_bin, account_no = bene.get("00", ""), bene.get("01", "")
    if not (bank_bin.isdigit() and len(bank_bin) == 6):
        raise ValueError("QR has no valid bank BIN")
    if not account_no.isalnum():
        raise ValueError("QR has no valid account number")

    amount = None
    if root.get("54", "").isdigit():
        amount = int(root["54"])
    memo = None
    if "62" in root:
        memo = _tlv(root["62"]).get("08") or None

    return ParsedBankQr(bank_bin, account_no, amount, memo)
