# app/tests/test_payments_bank_feed.py
# SePay webhook: authentication, idempotency, matching rules, manager workflow, HTTP.
# Runs against the FAKE business (payments_testkit); no billiard involved.
import hashlib
import hmac
import json
import time

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.payments import config
from app.payments.models.bank_transaction import BankTransaction
from app.payments.models.order import PaymentEvent, PaymentLine
from app.payments.models.payment import PaymentStatus, PaymentTransaction
from app.payments.routes.bank_feed_router import router as bank_feed_router
from app.payments.services.bank_feed_service import bank_feed_service as feed
from app.payments.services.order_service import payment_order_service as svc
from app.payments.utils.sepay import SepayAuthError, SepayNotConfigured, verify_request
from app.tests.payments_testkit import (  # noqa: F401  (fixtures are used by name)
    CLIENT, D, FAKE, cashier, db, engine, events, fake, make_user, manager, pay, view,
)

ACCOUNT = "0123456789"


@pytest.fixture(autouse=True)
def bank(monkeypatch):
    monkeypatch.setattr(config, "BANK_BIN", "970436")
    monkeypatch.setattr(config, "BANK_ACCOUNT_NO", ACCOUNT)
    monkeypatch.setattr(config, "BANK_CODE", "VCB")
    monkeypatch.setattr(config, "BANK_ACCOUNT_NAME", "BIDA CLUB")


def _transfer_line(db, user, fake, total="310000"):
    """A payable bill with one pending bank-transfer line. Returns (bill_id, line dict)."""
    bill_id = fake.create(total)
    pay(db, user, bill_id, payment_method="bank_transfer")
    return bill_id, view(db, user, bill_id)["payments"][0]


def _tx(tx_id, memo, amount=310000, **over):
    p = {
        "id": tx_id, "gateway": "Vietcombank", "transactionDate": "2026-10-19 18:05:00",
        "accountNumber": ACCOUNT, "code": None, "content": f"NGUYEN VAN A chuyen tien {memo} FT26292",
        "transferType": "in", "transferAmount": amount, "accumulated": 0,
        "subAccount": None, "referenceCode": "FT26292", "description": "",
    }
    p.update(over)
    return p


# ------------------------------------------------------------ authentication

def _sign(secret, body: bytes, ts):
    return "sha256=" + hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()


def test_api_key_auth():
    ok = {"Authorization": "Apikey s3cret"}
    assert verify_request(ok, b"{}", secret="", api_key="s3cret") == "api_key"
    for bad in ({}, {"Authorization": "Apikey nope"}, {"Authorization": "Bearer s3cret"}, {"Authorization": "s3cret"}):
        with pytest.raises(SepayAuthError):
            verify_request(bad, b"{}", secret="", api_key="s3cret")


def test_hmac_auth_signs_timestamp_dot_raw_body():
    body, ts = b'{"id": 1}', int(time.time())
    headers = {"X-SePay-Signature": _sign("k", body, ts), "X-SePay-Timestamp": str(ts)}
    assert verify_request(headers, body, secret="k", api_key="") == "hmac"
    with pytest.raises(SepayAuthError):                         # body tampered
        verify_request(headers, b'{"id": 2}', secret="k", api_key="")
    with pytest.raises(SepayAuthError):                         # wrong secret
        verify_request(headers, body, secret="other", api_key="")
    with pytest.raises(SepayAuthError):                         # missing headers
        verify_request({}, body, secret="k", api_key="")


def test_hmac_rejects_stale_timestamp_and_api_key_only_requests():
    body, old = b"{}", int(time.time()) - 301
    stale = {"X-SePay-Signature": _sign("k", body, old), "X-SePay-Timestamp": str(old)}
    with pytest.raises(SepayAuthError):
        verify_request(stale, body, secret="k", api_key="")
    with pytest.raises(SepayAuthError):                         # secret configured -> API key alone is not enough
        verify_request({"Authorization": "Apikey a"}, body, secret="k", api_key="a")


def test_unconfigured_endpoint_stays_closed():
    with pytest.raises(SepayNotConfigured):
        verify_request({"Authorization": "Apikey x"}, b"{}", secret="", api_key="")


# ------------------------------------------------------------------- matching

def test_exact_transfer_confirms_the_line_and_settles_the_business(db, cashier, fake):
    bill_id, line = _transfer_line(db, cashier, fake)
    memo = line["transfer"]["memo"]

    tx, dup = feed.process_sepay(db, _tx(9001, memo))

    assert dup is False and tx.status == "matched"
    order = svc.get_order(db, FAKE, bill_id)
    assert tx.order_id == order.id and tx.line_id == line["id"] and tx.client_id == CLIENT
    v = view(db, cashier, bill_id)
    assert v["state"] == "paid" and v["amount_paid"] == D("310000") and v["payments"][0]["status"] == "completed"
    bill = fake.bills[int(bill_id)]
    assert bill.state == "paid" and bill.paid_by_id is None     # settled by the system, not a person
    assert db.query(PaymentTransaction).one().status == PaymentStatus.COMPLETED
    assert events(db, bill_id)[-2:] == ["transfer_auto_confirmed", "order_paid"]
    ev = db.query(PaymentEvent).filter_by(event_type="transfer_auto_confirmed").one()
    assert ev.actor_id is None and ev.data["bank_transaction_id"] == tx.id and ev.data["reference_code"] == "FT26292"


def test_replayed_webhook_is_a_no_op(db, cashier, fake):
    bill_id, line = _transfer_line(db, cashier, fake)
    payload = _tx(9001, line["transfer"]["memo"])

    first, d1 = feed.process_sepay(db, payload)
    again, d2 = feed.process_sepay(db, payload)

    assert (d1, d2) == (False, True) and again.id == first.id and db.query(BankTransaction).count() == 1
    assert events(db, bill_id).count("transfer_auto_confirmed") == 1


def test_memo_is_found_in_messy_bank_content(db, cashier, fake):
    _, line = _transfer_line(db, cashier, fake)
    memo = line["transfer"]["memo"].lower()                     # banks may change the case
    tx, _ = feed.process_sepay(db, _tx(1, memo, content=f"MBVCB.123456.{memo}.CT tu 0987 NGUYEN VAN A"))
    assert tx.status == "matched"


def test_code_field_is_used_when_content_has_no_memo(db, cashier, fake):
    _, line = _transfer_line(db, cashier, fake)
    tx, _ = feed.process_sepay(db, _tx(1, "", content="chuyen khoan", code=line["transfer"]["memo"]))
    assert tx.status == "matched"


def test_memo_prefix_is_configurable(db, cashier, fake, monkeypatch):
    monkeypatch.setattr(config, "MEMO_PREFIX", "BIDA")
    _, line = _transfer_line(db, cashier, fake)
    assert line["transfer"]["memo"].startswith("BIDA")
    assert feed.process_sepay(db, _tx(1, line["transfer"]["memo"]))[0].status == "matched"


@pytest.mark.parametrize("amount", [300000, 320000])
def test_wrong_amount_is_never_auto_confirmed(db, cashier, fake, amount):
    bill_id, line = _transfer_line(db, cashier, fake)
    tx, _ = feed.process_sepay(db, _tx(5, line["transfer"]["memo"], amount=amount))

    assert tx.status == "needs_review" and "expected" in tx.reason
    assert tx.line_id == line["id"] and tx.client_id == CLIENT   # scoped to the club for review
    v = view(db, cashier, bill_id)
    assert v["state"] == "pending" and v["payments"][0]["status"] == "pending"


def test_unknown_code_and_missing_code_are_kept_unmatched(db, cashier, fake):
    _transfer_line(db, cashier, fake)
    no_code, _ = feed.process_sepay(db, _tx(1, "", content="tien com"))
    wrong, _ = feed.process_sepay(db, _tx(2, "PAY999L999"))
    assert (no_code.status, wrong.status) == ("unmatched", "unmatched")
    assert no_code.client_id is None and wrong.reason.endswith("PAY999L999")


def test_outgoing_and_other_account_are_ignored(db, cashier, fake):
    _, line = _transfer_line(db, cashier, fake)
    memo = line["transfer"]["memo"]
    out, _ = feed.process_sepay(db, _tx(1, memo, transferType="out"))
    other, _ = feed.process_sepay(db, _tx(2, memo, accountNumber="999"))
    assert (out.status, other.status) == ("ignored", "ignored")
    assert db.query(PaymentLine).one().status.value == "pending"        # nothing was confirmed


def test_second_transfer_for_a_paid_line_is_flagged_as_possible_duplicate(db, cashier, fake):
    _, line = _transfer_line(db, cashier, fake)
    memo = line["transfer"]["memo"]
    feed.process_sepay(db, _tx(1, memo))
    dupe, _ = feed.process_sepay(db, _tx(2, memo))
    assert dupe.status == "needs_review" and "already paid" in dupe.reason
    assert db.query(PaymentTransaction).count() == 1                    # still only one payment recorded


def test_money_for_a_cancelled_line_needs_review(db, cashier, fake):
    bill_id, line = _transfer_line(db, cashier, fake)
    svc.cancel_line(db, FAKE, bill_id, line["id"], cashier, "customer left")
    tx, _ = feed.process_sepay(db, _tx(1, line["transfer"]["memo"]))
    assert tx.status == "needs_review" and "cancelled" in tx.reason


def test_losing_a_race_for_the_line_is_flagged_not_lost(db, cashier, fake, monkeypatch):
    """The line is settled between the matcher's check and the lock: the second transfer must not vanish."""
    bill_id, line = _transfer_line(db, cashier, fake)
    real = svc.confirm_transfer_from_bank

    def settled_by_someone_else(*a, **kw):
        svc.confirm_transfer(db, FAKE, bill_id, line["id"], cashier)    # the cashier ticked "received" first
        return real(*a, **kw)                                           # now our confirm finds it completed

    monkeypatch.setattr(svc, "confirm_transfer_from_bank", settled_by_someone_else)
    tx, _ = feed.process_sepay(db, _tx(77, line["transfer"]["memo"]))

    assert tx.status == "needs_review" and "Could not confirm" in tx.reason
    assert db.query(PaymentTransaction).count() == 1                    # paid once, not twice


def test_split_bill_is_settled_by_the_bank_transfer_part(db, cashier, fake):
    bill_id = fake.create()
    pay(db, cashier, bill_id, payments=[
        {"method": "cash", "amount": 200000}, {"method": "bank_transfer", "amount": 110000}])
    transfer = view(db, cashier, bill_id)["payments"][1]

    tx, _ = feed.process_sepay(db, _tx(7, transfer["transfer"]["memo"], amount=110000))

    assert tx.status == "matched" and view(db, cashier, bill_id)["state"] == "paid"


def test_bad_payloads_are_rejected(db):
    with pytest.raises(ValueError):
        feed.process_sepay(db, {"content": "no id"})
    with pytest.raises(ValueError):
        feed.process_sepay(db, {"id": 1, "transferAmount": "abc"})
    assert db.query(BankTransaction).count() == 0


# ------------------------------------------------------------ manager workflow

def test_only_managers_can_list_assign_or_ignore(db, cashier):
    for call in (lambda: feed.list_transactions(db, cashier),
                 lambda: feed.assign(db, 1, 1, cashier),
                 lambda: feed.ignore(db, 1, cashier, None)):
        with pytest.raises(HTTPException) as e:
            call()
        assert e.value.status_code == 403


def test_manager_assigns_an_unmatched_transfer_to_a_line(db, cashier, manager, fake):
    bill_id, line = _transfer_line(db, cashier, fake)
    tx, _ = feed.process_sepay(db, _tx(1, "", content="chuyen tien ban 1"))
    assert tx.status == "unmatched"
    assert [t.id for t in feed.list_transactions(db, manager, "unmatched")] == [tx.id]

    done = feed.assign(db, tx.id, line["id"], manager)

    assert done.status == "matched" and done.handled_by_id == manager.id and done.line_id == line["id"]
    assert view(db, cashier, bill_id)["state"] == "paid"
    assert fake.bills[int(bill_id)].paid_by_id == manager.id
    assert "transfer_assigned_from_bank" in events(db, bill_id)
    with pytest.raises(HTTPException) as e:                      # cannot be assigned twice
        feed.assign(db, tx.id, line["id"], manager)
    assert e.value.status_code == 409


def test_assign_requires_the_exact_amount(db, cashier, manager, fake):
    bill_id, line = _transfer_line(db, cashier, fake)
    tx, _ = feed.process_sepay(db, _tx(1, "", content="x", transferAmount=300000))
    with pytest.raises(HTTPException) as e:
        feed.assign(db, tx.id, line["id"], manager)
    assert e.value.status_code == 422 and view(db, cashier, bill_id)["state"] == "pending"


def test_manager_can_ignore_with_a_note(db, cashier, manager, fake):
    _transfer_line(db, cashier, fake)
    tx, _ = feed.process_sepay(db, _tx(1, "PAY9L9", amount=50000))
    done = feed.ignore(db, tx.id, manager, "refunded to customer")
    assert done.status == "ignored" and done.note == "refunded to customer" and done.handled_by_id == manager.id


def test_other_clubs_manager_cannot_touch_a_matched_transaction(db, cashier, fake):
    _, line = _transfer_line(db, cashier, fake)
    tx, _ = feed.process_sepay(db, _tx(1, line["transfer"]["memo"], amount=1))   # needs_review, scoped to c1
    rival = make_user(db, "rival", role="manager", client="other")
    assert feed.list_transactions(db, rival) == []
    with pytest.raises(HTTPException) as e:
        feed.ignore(db, tx.id, rival, None)
    assert e.value.status_code == 404


# ---------------------------------------------------------------------- HTTP

@pytest.fixture()
def client(engine):
    Session = sessionmaker(bind=engine, autoflush=False)
    app = FastAPI()
    app.include_router(bank_feed_router)
    app.dependency_overrides[get_db] = lambda: Session()
    return TestClient(app)


def test_webhook_http_api_key_flow(client, db, cashier, fake, monkeypatch):
    monkeypatch.setattr(config, "SEPAY_API_KEY", "k123")
    bill_id, line = _transfer_line(db, cashier, fake)
    payload = _tx(42, line["transfer"]["memo"])
    url = "/payments/bank-feed/sepay"

    assert client.post(url, json=payload).status_code == 401
    assert client.post(url, json=payload, headers={"Authorization": "Apikey wrong"}).status_code == 401

    r = client.post(url, json=payload, headers={"Authorization": "Apikey k123"})
    assert r.status_code == 200 and r.json() == {"success": True}
    r = client.post(url, json=payload, headers={"Authorization": "Apikey k123"})        # SePay replay
    assert r.status_code == 200 and r.json() == {"success": True}

    db.expire_all()
    assert view(db, cashier, bill_id)["state"] == "paid" and db.query(BankTransaction).count() == 1


def test_webhook_http_hmac_uses_the_raw_body(client, db, cashier, fake, monkeypatch):
    monkeypatch.setattr(config, "SEPAY_WEBHOOK_SECRET", "topsecret")
    _, line = _transfer_line(db, cashier, fake)
    body = json.dumps(_tx(43, line["transfer"]["memo"]), separators=(",", ":")).encode()
    ts = int(time.time())
    headers = {"Content-Type": "application/json", "X-SePay-Timestamp": str(ts),
               "X-SePay-Signature": _sign("topsecret", body, ts)}
    url = "/payments/bank-feed/sepay"

    assert client.post(url, content=body, headers=headers).json() == {"success": True}
    bad = {**headers, "X-SePay-Signature": _sign("wrong", body, ts)}
    assert client.post(url, content=body, headers=bad).status_code == 401


def test_webhook_closed_when_not_configured_and_400_on_garbage(client, monkeypatch):
    url = "/payments/bank-feed/sepay"
    assert client.post(url, json={"id": 1}).status_code == 503
    monkeypatch.setattr(config, "SEPAY_API_KEY", "k")
    h = {"Authorization": "Apikey k"}
    assert client.post(url, content=b"not json", headers=h).status_code == 400
    assert client.post(url, json={"content": "no id"}, headers=h).status_code == 400
