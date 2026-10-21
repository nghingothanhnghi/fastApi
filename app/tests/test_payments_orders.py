# app/tests/test_payments_orders.py
# The Payments module on its own: cash (tendered/change), bank transfer (VietQR), split payments,
# cancel, manager-only void, Stripe gateway, audit trail. Runs against a FAKE business (see
# payments_testkit.FakePayable) to prove Payments only needs the PayableAdapter contract.
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.payments import config
from app.payments.models.payment import PaymentStatus, PaymentTransaction
from app.payments.schemas.order import PayOrderRequest
from app.payments.services.order_service import payment_order_service as svc
from app.payments.utils import vietqr
from app.tests.payments_testkit import (  # noqa: F401  (fixtures are used by name)
    CLIENT, D, FAKE, cashier, db, engine, events, fake, make_user, manager, pay, view,
)


@pytest.fixture()
def bank(monkeypatch):
    monkeypatch.setattr(config, "BANK_BIN", "970436")
    monkeypatch.setattr(config, "BANK_CODE", "VCB")
    monkeypatch.setattr(config, "BANK_ACCOUNT_NO", "0123456789")
    monkeypatch.setattr(config, "BANK_ACCOUNT_NAME", "BIDA CLUB")


# ------------------------------------------------------------------ VietQR

def test_crc16_ccitt_known_vector():
    assert vietqr.crc16_ccitt("123456789") == "29B1"


def _tlv(s):
    out, i = {}, 0
    while i < len(s):
        tag, n = s[i:i + 2], int(s[i + 2:i + 4])
        out[tag] = s[i + 4:i + 4 + n]
        i += 4 + n
    return out


def test_vietqr_payload_structure_and_crc():
    payload = vietqr.build_payload("970436", "0123456789", D("310000"), "PAY42L7")

    assert payload[-8:-4] == "6304" and vietqr.crc16_ccitt(payload[:-4]) == payload[-4:]
    top = _tlv(payload)
    assert top["01"] == "12" and top["53"] == "704" and top["54"] == "310000" and top["58"] == "VN"
    assert _tlv(top["62"])["08"] == "PAY42L7"
    merchant = _tlv(top["38"])
    assert merchant["00"] == "A000000727" and merchant["02"] == "QRIBFTTA"
    assert _tlv(merchant["01"]) == {"00": "970436", "01": "0123456789"}


@pytest.mark.parametrize("amount,memo", [(D("0"), "PAY1L1"), (D("1000"), "bad memo!")])
def test_vietqr_rejects_bad_input(amount, memo):
    with pytest.raises(ValueError):
        vietqr.build_payload("970436", "1", amount, memo)


def test_memo_uses_the_configured_prefix(monkeypatch):
    assert vietqr.make_memo(12, 34) == "PAY12L34"
    monkeypatch.setattr(config, "MEMO_PREFIX", "BIDA")
    assert vietqr.make_memo(12, 34) == "BIDA12L34"


# ------------------------------------------------------------ request schema

def test_request_needs_exactly_one_style():
    with pytest.raises(ValidationError):
        PayOrderRequest()
    with pytest.raises(ValidationError):
        PayOrderRequest(payment_method="cash", payments=[{"method": "cash", "amount": 1}])
    with pytest.raises(ValidationError):
        PayOrderRequest(payment_method="bank_transfer", cash_tendered=500000)
    with pytest.raises(ValidationError):
        PayOrderRequest(payments=[{"method": "bank_transfer", "amount": 1, "cash_tendered": 5}])


# --------------------------------------------------------------------- cash

def test_cash_with_tendered_gives_change_and_settles_the_business(db, cashier, fake):
    bill_id = fake.create("310000")

    order, gateway = pay(db, cashier, bill_id, payment_method="cash", cash_tendered=500000)
    v = view(db, cashier, bill_id)

    assert gateway is None and order.state.value == "paid"
    assert v["state"] == "paid" and v["method"] == "cash"
    assert v["amount_paid"] == D("310000") and v["balance_due"] == 0 and v["total"] == D("310000")
    (line,) = v["payments"]
    assert line["cash_tendered"] == D("500000") and line["change_given"] == D("190000")
    assert line["status"] == "completed" and line["payment_reference"]
    assert events(db, bill_id) == ["line_created", "cash_received", "order_paid"]
    # the business object was told, so it never has to join the Payments tables
    bill = fake.bills[int(bill_id)]
    assert bill.state == "paid" and bill.method == "cash" and bill.paid_by_id == cashier.id
    # the Payments module's own record is the source of truth for the money
    tx = db.query(PaymentTransaction).one()
    assert tx.provider == "manual" and tx.status == PaymentStatus.COMPLETED and tx.amount == 310000
    assert tx.currency == "VND" and tx.extra_metadata["fake_bill_id"] == int(bill_id)
    assert tx.extra_metadata["payment_order_id"] == order.id


def test_cash_without_tendered_is_exact_amount(db, cashier, fake):
    bill_id = fake.create()
    pay(db, cashier, bill_id, payment_method="cash")
    (line,) = view(db, cashier, bill_id)["payments"]
    assert line["cash_tendered"] == D("310000") and line["change_given"] == 0


def test_cash_tendered_below_amount_is_rejected_and_nothing_recorded(db, cashier, fake):
    bill_id = fake.create()
    with pytest.raises(HTTPException) as e:
        pay(db, cashier, bill_id, payment_method="cash", cash_tendered=100000)
    assert e.value.status_code == 422
    assert view(db, cashier, bill_id)["payments"] == [] and db.query(PaymentTransaction).count() == 0


def test_paying_twice_is_rejected(db, cashier, fake):
    bill_id = fake.create()
    pay(db, cashier, bill_id, payment_method="cash")
    with pytest.raises(HTTPException) as e:
        pay(db, cashier, bill_id, payment_method="cash")
    assert e.value.status_code == 409


# --------------------------------------------------- the business owns the amount

def test_business_decides_when_and_how_much(db, cashier, fake):
    not_ready = fake.create(ready=False)
    with pytest.raises(HTTPException) as e:
        pay(db, cashier, not_ready, payment_method="cash")
    assert e.value.status_code == 409 and "not finished" in e.value.detail

    free = fake.create("0")
    with pytest.raises(HTTPException) as e:
        pay(db, cashier, free, payment_method="cash")
    assert e.value.status_code == 409 and "Nothing to pay" in e.value.detail


def test_amount_follows_the_business_not_a_stale_snapshot(db, cashier, fake):
    bill_id = fake.create("310000")
    pay(db, cashier, bill_id, payment_method="bank_transfer")        # order created at 310000, pending
    fake.bills[int(bill_id)].total = D("350000")                     # e.g. a drink was added

    v = view(db, cashier, bill_id)

    assert v["total"] == D("350000") and v["balance_due"] == D("350000")


def test_unknown_source_and_other_clubs_get_404(db, cashier, fake):
    bill_id = fake.create()
    with pytest.raises(HTTPException) as e:
        svc.get_view(db, "nope", bill_id, cashier)
    assert e.value.status_code == 404
    stranger = make_user(db, "stranger", client="other")
    with pytest.raises(HTTPException) as e:
        svc.get_view(db, FAKE, bill_id, stranger)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        pay(db, stranger, bill_id, payment_method="cash")
    assert e.value.status_code == 404


def test_order_view_before_any_payment(db, cashier, fake):
    v = view(db, cashier, fake.create("310000"))
    assert (v["state"], v["order_id"], v["amount_paid"], v["balance_due"], v["payments"]) == \
        ("unpaid", None, 0, D("310000"), [])


# ----------------------------------------------------------------- transfer

def test_transfer_stays_pending_with_qr_until_cashier_confirms(db, cashier, fake, bank):
    bill_id = fake.create()

    order, _ = pay(db, cashier, bill_id, payment_method="bank_transfer")
    v = view(db, cashier, bill_id)

    assert v["state"] == "pending" and v["amount_paid"] == 0 and v["balance_due"] == D("310000")
    (line,) = v["payments"]
    assert line["status"] == "pending"
    t = line["transfer"]
    assert t["memo"] == f"PAY{order.id}L{line['id']}" and t["amount"] == D("310000")
    assert t["qr_payload"] and vietqr.crc16_ccitt(t["qr_payload"][:-4]) == t["qr_payload"][-4:]
    assert "VCB-0123456789" in t["qr_image_url"] and "amount=310000" in t["qr_image_url"]
    assert t["expires_at"] is not None
    assert fake.bills[int(bill_id)].state == "pending"

    svc.confirm_transfer(db, FAKE, bill_id, line["id"], cashier, note="saw it on the app")
    v = view(db, cashier, bill_id)
    assert v["state"] == "paid" and v["method"] == "bank_transfer" and v["payments"][0]["transfer"] is None
    assert db.query(PaymentTransaction).one().status == PaymentStatus.COMPLETED
    assert events(db, bill_id) == ["line_created", "transfer_awaiting", "transfer_confirmed", "order_paid"]


def test_transfer_without_bank_configured_has_no_qr(db, cashier, fake, monkeypatch):
    monkeypatch.setattr(config, "BANK_BIN", "")
    pay(db, cashier, bill_id := fake.create(), payment_method="bank_transfer")
    t = view(db, cashier, bill_id)["payments"][0]["transfer"]
    assert t["qr_payload"] is None and t["memo"]


def test_transfer_auto_confirm_switch_keeps_old_behaviour(db, cashier, fake, monkeypatch):
    monkeypatch.setattr(config, "BANK_TRANSFER_REQUIRES_CONFIRMATION", False)
    pay(db, cashier, bill_id := fake.create(), payment_method="bank_transfer")
    assert view(db, cashier, bill_id)["state"] == "paid"


def test_confirm_transfer_is_idempotent_and_rejects_cash_lines(db, cashier, fake):
    bill_id = fake.create()
    pay(db, cashier, bill_id, payments=[
        {"method": "cash", "amount": 100000}, {"method": "bank_transfer", "amount": 210000}])
    cash, transfer = view(db, cashier, bill_id)["payments"]

    with pytest.raises(HTTPException) as e:
        svc.confirm_transfer(db, FAKE, bill_id, cash["id"], cashier)
    assert e.value.status_code == 409

    svc.confirm_transfer(db, FAKE, bill_id, transfer["id"], cashier)
    svc.confirm_transfer(db, FAKE, bill_id, transfer["id"], cashier)          # second tick is a no-op
    assert db.query(PaymentTransaction).filter_by(status=PaymentStatus.COMPLETED).count() == 2
    with pytest.raises(HTTPException) as e:
        svc.confirm_transfer(db, FAKE, bill_id, 9999, cashier)
    assert e.value.status_code == 404


# -------------------------------------------------------------------- split

def test_split_cash_and_transfer(db, cashier, fake, bank):
    bill_id = fake.create()

    pay(db, cashier, bill_id, payments=[
        {"method": "cash", "amount": 200000, "cash_tendered": 200000},
        {"method": "bank_transfer", "amount": 110000},
    ])
    v = view(db, cashier, bill_id)

    assert v["state"] == "pending" and v["method"] == "split"
    assert v["amount_paid"] == D("200000") and v["balance_due"] == D("110000")
    assert [p["status"] for p in v["payments"]] == ["completed", "pending"]
    with pytest.raises(HTTPException) as e:                       # a second /pay while the transfer awaits
        pay(db, cashier, bill_id, payment_method="cash")
    assert e.value.status_code == 409

    svc.confirm_transfer(db, FAKE, bill_id, v["payments"][1]["id"], cashier)
    v = view(db, cashier, bill_id)
    assert v["state"] == "paid" and v["amount_paid"] == D("310000") and v["paid_at"] is not None


def test_split_that_does_not_add_up_is_rejected(db, cashier, fake):
    bill_id = fake.create()
    with pytest.raises(HTTPException) as e:
        pay(db, cashier, bill_id, payments=[
            {"method": "cash", "amount": 100000}, {"method": "bank_transfer", "amount": 100000}])
    assert e.value.status_code == 422 and db.query(PaymentTransaction).count() == 0


def test_split_between_two_cash_lines_settles_immediately(db, cashier, fake):
    bill_id = fake.create()
    pay(db, cashier, bill_id, payments=[
        {"method": "cash", "amount": 10000}, {"method": "cash", "amount": 300000, "cash_tendered": 500000}])
    v = view(db, cashier, bill_id)
    assert v["state"] == "paid" and [p["change_given"] for p in v["payments"]] == [D("0"), D("200000")]


def test_cancel_transfer_then_pay_the_balance_with_cash(db, cashier, fake):
    bill_id = fake.create()
    pay(db, cashier, bill_id, payments=[
        {"method": "cash", "amount": 200000}, {"method": "bank_transfer", "amount": 110000}])
    transfer = view(db, cashier, bill_id)["payments"][1]

    svc.cancel_line(db, FAKE, bill_id, transfer["id"], cashier, reason="customer has no signal")
    v = view(db, cashier, bill_id)
    assert v["state"] == "pending" and v["balance_due"] == D("110000") and v["payments"][1]["status"] == "cancelled"
    failed = db.query(PaymentTransaction).filter_by(status=PaymentStatus.FAILED).one()
    assert failed.extra_metadata["fake_bill_id"] == int(bill_id)           # reconciliation info kept
    assert failed.extra_metadata["cancel_reason"] == "customer has no signal"

    with pytest.raises(HTTPException) as e:                                # only the balance can be paid now
        pay(db, cashier, bill_id, payments=[{"method": "cash", "amount": 310000}])
    assert e.value.status_code == 422

    pay(db, cashier, bill_id, payment_method="cash", cash_tendered=200000)
    v = view(db, cashier, bill_id)
    assert v["state"] == "paid" and v["amount_paid"] == D("310000") and v["payments"][2]["change_given"] == D("90000")
    assert "line_cancelled" in events(db, bill_id)


def test_cancelling_the_only_pending_line_releases_the_bill(db, cashier, fake):
    bill_id = fake.create()
    pay(db, cashier, bill_id, payment_method="bank_transfer")
    svc.cancel_line(db, FAKE, bill_id, view(db, cashier, bill_id)["payments"][0]["id"], cashier)

    assert view(db, cashier, bill_id)["state"] == "unpaid" and fake.bills[int(bill_id)].state == "unpaid"
    pay(db, cashier, bill_id, payment_method="cash")                       # the cashier can start over
    assert view(db, cashier, bill_id)["state"] == "paid"


def test_cannot_cancel_a_completed_line(db, cashier, fake):
    bill_id = fake.create()
    pay(db, cashier, bill_id, payment_method="cash")
    with pytest.raises(HTTPException) as e:
        svc.cancel_line(db, FAKE, bill_id, view(db, cashier, bill_id)["payments"][0]["id"], cashier)
    assert e.value.status_code == 409


# --------------------------------------------------------------------- void

def test_only_a_manager_can_void_and_a_reason_is_required(db, cashier, manager, fake):
    bill_id = fake.create()
    pay(db, cashier, bill_id, payment_method="cash")
    line_id = view(db, cashier, bill_id)["payments"][0]["id"]

    with pytest.raises(HTTPException) as e:
        svc.void_line(db, FAKE, bill_id, line_id, cashier, "customer changed mind")
    assert e.value.status_code == 403 and view(db, cashier, bill_id)["state"] == "paid"
    for bad in ("", "  ", "x"):
        with pytest.raises(HTTPException) as e:
            svc.void_line(db, FAKE, bill_id, line_id, manager, bad)
        assert e.value.status_code == 422


def test_void_reopens_the_bill_refunds_the_payment_and_is_audited(db, cashier, manager, fake):
    bill_id = fake.create()
    pay(db, cashier, bill_id, payment_method="cash")
    line_id = view(db, cashier, bill_id)["payments"][0]["id"]

    svc.void_line(db, FAKE, bill_id, line_id, manager, "wrong table charged")
    v = view(db, cashier, bill_id)

    assert v["state"] == "unpaid" and v["paid_at"] is None
    assert v["amount_paid"] == 0 and v["balance_due"] == D("310000")
    assert v["payments"][0]["status"] == "voided" and v["payments"][0]["void_reason"] == "wrong table charged"
    bill = fake.bills[int(bill_id)]
    assert bill.state == "unpaid" and bill.paid_at is None and bill.paid_by_id is None
    assert db.query(PaymentTransaction).one().status == PaymentStatus.REFUNDED
    voided = [e for e in svc.list_events(db, FAKE, bill_id, manager) if e.event_type == "line_voided"]
    assert len(voided) == 1 and voided[0].actor_id == manager.id and voided[0].data["reason"] == "wrong table charged"

    pay(db, cashier, bill_id, payment_method="cash")                       # the cashier can take the money again
    assert view(db, cashier, bill_id)["state"] == "paid"
    with pytest.raises(HTTPException) as e:                                # a voided line can't be voided twice
        svc.void_line(db, FAKE, bill_id, line_id, manager, "again")
    assert e.value.status_code == 409


def test_voiding_one_line_of_a_split_leaves_the_bill_part_paid(db, cashier, manager, fake):
    bill_id = fake.create()
    pay(db, cashier, bill_id, payments=[{"method": "cash", "amount": 100000}, {"method": "cash", "amount": 210000}])
    first = view(db, cashier, bill_id)["payments"][0]

    svc.void_line(db, FAKE, bill_id, first["id"], manager, "gave too much")
    v = view(db, cashier, bill_id)

    assert v["state"] == "pending" and v["amount_paid"] == D("210000") and v["balance_due"] == D("100000")


def test_cannot_void_a_pending_line(db, cashier, manager, fake):
    bill_id = fake.create()
    pay(db, cashier, bill_id, payment_method="bank_transfer")
    with pytest.raises(HTTPException) as e:
        svc.void_line(db, FAKE, bill_id, view(db, cashier, bill_id)["payments"][0]["id"], manager, "not paid yet")
    assert e.value.status_code == 409


# ------------------------------------------------------------ audit + tenants

def test_events_are_tenant_scoped(db, cashier, fake):
    bill_id = fake.create()
    pay(db, cashier, bill_id, payment_method="cash")
    assert [e.event_type for e in svc.list_events(db, FAKE, bill_id, cashier)][-1] == "order_paid"
    assert svc.list_events(db, FAKE, fake.create(), cashier) == []        # no order yet
    with pytest.raises(HTTPException) as e:
        svc.list_events(db, FAKE, bill_id, make_user(db, "x", client="other"))
    assert e.value.status_code == 404


# ------------------------------------------------------------------- gateway

def _intent(status):
    return SimpleNamespace(id="pi_1", client_secret="sec", status=status)


def test_stripe_creates_a_pending_payment_then_settles_on_confirm(db, cashier, fake):
    bill_id = fake.create("310000")
    with patch("stripe.PaymentIntent.create", return_value=_intent("requires_payment_method")) as create:
        order, gateway = pay(db, cashier, bill_id, payment_method="stripe")

    create.assert_called_once()
    assert create.call_args.kwargs["amount"] == 310000 and create.call_args.kwargs["currency"] == "vnd"
    assert gateway["client_secret"] == "sec" and order.state.value == "pending" and order.method == "stripe"
    assert fake.bills[int(bill_id)].state == "pending"

    with patch("stripe.PaymentIntent.retrieve", return_value=_intent("succeeded")):
        svc.confirm_gateway(db, FAKE, bill_id, cashier)

    v = view(db, cashier, bill_id)
    assert v["state"] == "paid" and v["method"] == "stripe" and fake.bills[int(bill_id)].state == "paid"


def test_stripe_failure_lets_the_cashier_retry(db, cashier, fake):
    bill_id = fake.create()
    with patch("stripe.PaymentIntent.create", return_value=_intent("requires_payment_method")):
        pay(db, cashier, bill_id, payment_method="stripe")
    with patch("stripe.PaymentIntent.retrieve", return_value=_intent("requires_payment_method")):
        svc.confirm_gateway(db, FAKE, bill_id, cashier)
    assert view(db, cashier, bill_id)["state"] == "unpaid" and fake.bills[int(bill_id)].state == "unpaid"


def test_stripe_error_releases_the_claim(db, cashier, fake):
    bill_id = fake.create()
    with patch("stripe.PaymentIntent.create", side_effect=RuntimeError("stripe down")):
        with pytest.raises(RuntimeError):
            pay(db, cashier, bill_id, payment_method="stripe")
    assert view(db, cashier, bill_id)["state"] == "unpaid" and fake.bills[int(bill_id)].state == "unpaid"


def test_stripe_cannot_be_mixed_with_cash_lines_and_needs_a_gateway_payment_to_confirm(db, cashier, fake):
    bill_id = fake.create()
    pay(db, cashier, bill_id, payments=[{"method": "cash", "amount": 10000}, {"method": "bank_transfer", "amount": 300000}])
    with pytest.raises(HTTPException) as e:
        pay(db, cashier, bill_id, payment_method="stripe")
    assert e.value.status_code == 409
    with pytest.raises(HTTPException) as e:                                # no gateway payment to confirm
        svc.confirm_gateway(db, FAKE, bill_id, cashier)
    assert e.value.status_code == 409
