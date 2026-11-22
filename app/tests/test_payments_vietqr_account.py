from decimal import Decimal
from types import SimpleNamespace

from app.payments import config
from app.payments.utils import vietqr
from app.payments.utils.vietqr_parser import parse_vietqr

ACC = SimpleNamespace(bank_bin="970436", bank_code="VCB", account_no="0123456789", account_name="CLUB A")


def test_club_account_drives_qr_and_roundtrips():
    ins = vietqr.build_transfer_instruction(Decimal("50000"), "PAY1L2", None, account=ACC)
    p = parse_vietqr(ins["qr_payload"])
    assert (p.bank_bin, p.account_no, p.amount, p.memo) == ("970436", "0123456789", 50000, "PAY1L2")
    assert ins["account_name"] == "CLUB A"
    assert "VCB-0123456789" in ins["qr_image_url"]


def test_without_account_falls_back_to_config(monkeypatch):
    monkeypatch.setattr(config, "BANK_BIN", "970422")
    monkeypatch.setattr(config, "BANK_CODE", "MB")
    monkeypatch.setattr(config, "BANK_ACCOUNT_NO", "999")
    monkeypatch.setattr(config, "BANK_ACCOUNT_NAME", "ENV")
    ins = vietqr.build_transfer_instruction(Decimal("1000"), "PAY1L1", None)
    assert parse_vietqr(ins["qr_payload"]).account_no == "999"


def test_nothing_configured_gives_no_qr(monkeypatch):
    for k in ("BANK_BIN", "BANK_CODE", "BANK_ACCOUNT_NO", "BANK_ACCOUNT_NAME"):
        monkeypatch.setattr(config, k, "")
    ins = vietqr.build_transfer_instruction(Decimal("1000"), "PAY1L1", None)
    assert ins["qr_payload"] is None and ins["qr_image_url"] is None


def test_bin_only_account_uses_bin_in_image_url():
    acc = SimpleNamespace(bank_bin="970436", bank_code=None, account_no="123456", account_name="")
    assert "970436-123456" in vietqr.build_image_url(Decimal("1000"), "PAY1L1", acc)
