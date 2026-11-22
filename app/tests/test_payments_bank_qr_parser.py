import pytest

from app.payments.utils.vietqr_parser import _crc16_ccitt, parse_vietqr


def _f(tag, value):
    return f"{tag}{len(value):02d}{value}"


def make_qr(bank_bin="970436", account="0123456789", service="QRIBFTTA", amount=None, memo=None):
    benef = _f("00", bank_bin) + _f("01", account)
    merchant = _f("00", "A000000727") + _f("01", benef) + _f("02", service)
    body = _f("00", "01") + _f("01", "12" if amount or memo else "11") + _f("38", merchant) + _f("53", "704")
    if amount:
        body += _f("54", str(amount))
    body += _f("58", "VN")
    if memo:
        body += _f("62", _f("08", memo))
    body += "6304"
    return body + _crc16_ccitt(body)


def test_parses_bin_and_account():
    p = parse_vietqr(make_qr())
    assert (p.bank_bin, p.account_no, p.amount, p.memo) == ("970436", "0123456789", None, None)


def test_parses_amount_and_memo():
    p = parse_vietqr(make_qr(amount=50000, memo="PAY1L2"))
    assert p.amount == 50000 and p.memo == "PAY1L2"


def test_bad_checksum_rejected():
    qr = make_qr()
    bad = qr[:-1] + ("0" if qr[-1] != "0" else "1")
    with pytest.raises(ValueError, match="checksum"):
        parse_vietqr(bad)


def test_card_qr_rejected():
    with pytest.raises(ValueError, match="card"):
        parse_vietqr(make_qr(service="QRIBFTTC"))


@pytest.mark.parametrize("text", ["", "hello", "https://example.com/pay?id=1"])
def test_non_bank_text_rejected(text):
    with pytest.raises(ValueError):
        parse_vietqr(text)
