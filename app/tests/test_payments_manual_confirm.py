# app/tests/test_payments_manual_confirm.py
import pytest
from fastapi import HTTPException

from app.payments import config
from app.payments.services.order_service import payment_order_service as svc
from app.tests.test_payments_testkit import (  # noqa: F401
    FAKE, cashier, db, engine, fake, manager, pay, view,
)


def _pending_transfer(db, user, fake):
    bill_id = fake.create()
    pay(db, user, bill_id, payment_method="bank_transfer")
    return bill_id, view(db, user, bill_id)["payments"][0]["id"]


def test_default_lets_a_cashier_confirm_without_a_note(db, cashier, fake):
    bill_id, line_id = _pending_transfer(db, cashier, fake)
    svc.confirm_transfer(db, FAKE, bill_id, line_id, cashier)
    assert view(db, cashier, bill_id)["state"] == "paid"


def test_manager_only_flag_blocks_a_cashier_but_not_a_manager(
    db, cashier, manager, fake, monkeypatch
):
    monkeypatch.setattr(config, "MANUAL_CONFIRM_REQUIRES_MANAGER", True)
    monkeypatch.setattr(config, "MANUAL_CONFIRM_REQUIRES_NOTE", False)

    bill_id, line_id = _pending_transfer(db, cashier, fake)

    with pytest.raises(HTTPException) as e:
        svc.confirm_transfer(db, FAKE, bill_id, line_id, cashier)

    assert e.value.status_code == 403
    assert view(db, cashier, bill_id)["payments"][0]["status"] == "pending"

    svc.confirm_transfer(db, FAKE, bill_id, line_id, manager)
    assert view(db, cashier, bill_id)["state"] == "paid"


@pytest.mark.parametrize("note", [None, "", "  ", "x"])
def test_note_flag_rejects_missing_or_tiny_notes(db, cashier, fake, monkeypatch, note):
    monkeypatch.setattr(config, "MANUAL_CONFIRM_REQUIRES_MANAGER", False)
    monkeypatch.setattr(config, "MANUAL_CONFIRM_REQUIRES_NOTE", True)
    bill_id, line_id = _pending_transfer(db, cashier, fake)
    with pytest.raises(HTTPException) as e:
        svc.confirm_transfer(db, FAKE, bill_id, line_id, cashier, note=note)
    assert e.value.status_code == 422
    assert view(db, cashier, bill_id)["state"] == "pending"


def test_note_flag_accepts_a_real_note_and_stores_it(db, cashier, fake, monkeypatch):
    monkeypatch.setattr(config, "MANUAL_CONFIRM_REQUIRES_MANAGER", False)
    monkeypatch.setattr(config, "MANUAL_CONFIRM_REQUIRES_NOTE", True)

    bill_id, line_id = _pending_transfer(db, cashier, fake)

    svc.confirm_transfer(
        db, FAKE, bill_id, line_id, cashier,
        note="VCB app, ref FT26301"
    )

    v = view(db, cashier, bill_id)
    assert v["state"] == "paid"
    assert v["payments"][0]["note"] == "VCB app, ref FT26301"


def test_repeat_confirm_stays_idempotent_even_with_flags_on(db, cashier, fake, monkeypatch):
    bill_id, line_id = _pending_transfer(db, cashier, fake)
    svc.confirm_transfer(db, FAKE, bill_id, line_id, cashier)
    monkeypatch.setattr(config, "MANUAL_CONFIRM_REQUIRES_MANAGER", True)
    svc.confirm_transfer(db, FAKE, bill_id, line_id, cashier)   # already paid: no error