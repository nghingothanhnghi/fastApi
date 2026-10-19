# app/tests/test_billiard_bank_feed.py
# SePay webhook: authentication, idempotency, matching rules, manager workflow.
import hashlib
import hmac
import json
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

# app.database / app.core.config validate env at import time.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/billiard_test_import.db")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
import app.billiard.models  # noqa: F401  (registers billiard tables)
from app.billiard import config
from app.billiard.models import (
    BankTransaction, BilliardTable, PaymentState, SessionPaymentEvent, SessionPayment,
)
from app.billiard.routes.bank_feed_router import router as bank_feed_router
from app.billiard.schemas.session import PaySessionRequest
from app.billiard.services.bank_feed_service import bank_feed_service as feed
from app.billiard.services.payment_service import billiard_payment_service as svc
from app.billiard.services.session_lifecycle import finalize_stop, open_session
from app.billiard.services.session_service import session_service
from app.billiard.utils.sepay import SepayAuthError, SepayNotConfigured, verify_request
from app.payments.models.payment import PaymentTransaction, PaymentStatus
from app.product.models.product import Product, ProductVariant  # noqa: F401  (session_items FK)
from app.user.models.user import User
from app.user.models.role import Role
from app.user.models.user_role import UserRole
from app.hydro_system.models.device import HydroDevice  # noqa: F401
from app.hydro_system.models.actuator import HydroActuator  # noqa: F401
from app.hydro_system.models.actuator_log import HydroActuatorLog  # noqa: F401
from app.hydro_system.models.schedule import HydroSchedule  # noqa: F401
from app.user.utils.token import get_current_user

CLIENT = "c1"
ACCOUNT = "0123456789"
D = Decimal


@pytest.fixture()
def engine():
    e = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(e)
    return e


@pytest.fixture()
def db(engine):
    s = sessionmaker(bind=engine, autoflush=False)()
    yield s
    s.close()


@pytest.fixture(autouse=True)
def bank(monkeypatch):
    monkeypatch.setattr(config, "BANK_BIN", "970436")
    monkeypatch.setattr(config, "BANK_ACCOUNT_NO", ACCOUNT)
    monkeypatch.setattr(config, "BANK_CODE", "VCB")
    monkeypatch.setattr(config, "BANK_ACCOUNT_NAME", "BIDA CLUB")


def _user(db, name, role=None, client=CLIENT):
    u = User(client_id=client, username=name, email=f"{name}@x.com", hashed_password="x")
    db.add(u)
    db.flush()
    if role:
        r = db.query(Role).filter_by(name=role).first() or Role(name=role, display_name=role, is_active=True)
        db.add(r)
        db.flush()
        db.add(UserRole(user_id=u.id, role_id=r.id))
    db.commit()
    return u


@pytest.fixture()
def cashier(db):
    return _user(db, "cashier")


@pytest.fixture()
def manager(db):
    return _user(db, "boss", role="manager")


def _transfer_line(db, user, rate="310000"):
    """A completed 1h session with one pending bank-transfer line. Returns (session_id, line dict)."""
    table = BilliardTable(name="T1", hourly_rate=D(rate), client_id=CLIENT)
    db.add(table)
    db.flush()
    start = datetime.now(timezone.utc) - timedelta(hours=2)
    s = open_session(db, table, user.id, at=start)
    finalize_stop(db, s, table, user.id, at=start + timedelta(minutes=60))
    db.commit()
    sid = s.id
    session, _ = svc.pay_session(db, sid, PaySessionRequest(payment_method="bank_transfer"), user)
    return sid, session_service.build_bill(session)["payments"][0]


def _tx(tx_id, memo, amount=310000, **over):
    p = {
        "id": tx_id, "gateway": "Vietcombank", "transactionDate": "2026-10-19 18:05:00",
        "accountNumber": ACCOUNT, "code": None, "content": f"NGUYEN VAN A chuyen tien {memo} FT26292",
        "transferType": "in", "transferAmount": amount, "accumulated": 0,
        "subAccount": None, "referenceCode": "FT26292", "description": "",
    }
    p.update(over)
    return p


def _bill(db, user, sid):
    return session_service.build_bill(session_service.get_session(db, sid, user))


def _events(db, sid):
    return [e.event_type for e in db.query(SessionPaymentEvent)
            .filter(SessionPaymentEvent.session_id == sid).order_by(SessionPaymentEvent.id)]


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


# ------------------------------------------------------------------ matching

def test_exact_transfer_confirms_the_line_and_pays_the_bill(db, cashier):
    sid, line = _transfer_line(db, cashier)
    memo = line["transfer"]["memo"]

    tx, dup = feed.process_sepay(db, _tx(9001, memo))

    assert dup is False and tx.status == "matched"
    assert tx.session_id == sid and tx.line_id == line["id"] and tx.client_id == CLIENT
    bill = _bill(db, cashier, sid)
    assert bill["payment_state"] == "paid" and bill["amount_paid"] == D("310000")
    assert bill["payments"][0]["status"] == "completed"
    assert bill["paid_by"] is None                              # confirmed by the system, not a person
    assert db.query(PaymentTransaction).one().status == PaymentStatus.COMPLETED
    assert _events(db, sid)[-2:] == ["transfer_auto_confirmed", "session_paid"]
    ev = db.query(SessionPaymentEvent).filter_by(event_type="transfer_auto_confirmed").one()
    assert ev.actor_id is None and ev.data["bank_transaction_id"] == tx.id and ev.data["reference_code"] == "FT26292"


def test_replayed_webhook_is_a_no_op(db, cashier):
    sid, line = _transfer_line(db, cashier)
    payload = _tx(9001, line["transfer"]["memo"])

    first, d1 = feed.process_sepay(db, payload)
    again, d2 = feed.process_sepay(db, payload)

    assert (d1, d2) == (False, True) and again.id == first.id
    assert db.query(BankTransaction).count() == 1
    assert _events(db, sid).count("transfer_auto_confirmed") == 1


def test_memo_is_found_in_messy_bank_content(db, cashier):
    sid, line = _transfer_line(db, cashier)
    memo = line["transfer"]["memo"].lower()                     # banks may change the case
    tx, _ = feed.process_sepay(db, _tx(1, memo, content=f"MBVCB.123456.{memo}.CT tu 0987 NGUYEN VAN A"))
    assert tx.status == "matched"


def test_code_field_is_used_when_content_has_no_memo(db, cashier):
    sid, line = _transfer_line(db, cashier)
    tx, _ = feed.process_sepay(db, _tx(1, "", content="chuyen khoan", code=line["transfer"]["memo"]))
    assert tx.status == "matched"


@pytest.mark.parametrize("amount,word", [(300000, "expected"), (320000, "expected")])
def test_wrong_amount_is_never_auto_confirmed(db, cashier, amount, word):
    sid, line = _transfer_line(db, cashier)
    tx, _ = feed.process_sepay(db, _tx(5, line["transfer"]["memo"], amount=amount))

    assert tx.status == "needs_review" and word in tx.reason
    assert tx.line_id == line["id"] and tx.client_id == CLIENT   # scoped to the club for review
    bill = _bill(db, cashier, sid)
    assert bill["payment_state"] == "pending" and bill["payments"][0]["status"] == "pending"


def test_unknown_code_and_missing_code_are_kept_unmatched(db, cashier):
    _transfer_line(db, cashier)
    no_code, _ = feed.process_sepay(db, _tx(1, "", content="tien com"))
    wrong, _ = feed.process_sepay(db, _tx(2, "BIDA999L999"))
    assert (no_code.status, wrong.status) == ("unmatched", "unmatched")
    assert no_code.client_id is None and wrong.reason.endswith("BIDA999L999")


def test_outgoing_and_other_account_are_ignored(db, cashier):
    _, line = _transfer_line(db, cashier)
    memo = line["transfer"]["memo"]
    out, _ = feed.process_sepay(db, _tx(1, memo, transferType="out"))
    other, _ = feed.process_sepay(db, _tx(2, memo, accountNumber="999"))
    assert (out.status, other.status) == ("ignored", "ignored")
    assert db.query(SessionPayment).one().status.value == "pending"   # nothing was confirmed


def test_second_transfer_for_a_paid_line_is_flagged_as_possible_duplicate(db, cashier):
    sid, line = _transfer_line(db, cashier)
    memo = line["transfer"]["memo"]
    feed.process_sepay(db, _tx(1, memo))
    dupe, _ = feed.process_sepay(db, _tx(2, memo))
    assert dupe.status == "needs_review" and "already paid" in dupe.reason
    assert db.query(PaymentTransaction).count() == 1                   # still only one payment recorded


def test_money_for_a_cancelled_line_needs_review(db, cashier):
    sid, line = _transfer_line(db, cashier)
    svc.cancel_line(db, sid, line["id"], cashier, "customer left")
    tx, _ = feed.process_sepay(db, _tx(1, line["transfer"]["memo"]))
    assert tx.status == "needs_review" and "cancelled" in tx.reason


def test_losing_a_race_for_the_line_is_flagged_not_lost(db, cashier, monkeypatch):
    """Line is settled between the matcher's check and the lock: the second transfer must not vanish."""
    sid, line = _transfer_line(db, cashier)
    memo = line["transfer"]["memo"]
    real = svc.confirm_transfer_from_bank

    def settled_by_someone_else(*a, **kw):
        svc.confirm_transfer(db, sid, line["id"], cashier)        # the cashier ticked "received" first
        return real(*a, **kw)                                     # now our confirm finds it completed

    monkeypatch.setattr(svc, "confirm_transfer_from_bank", settled_by_someone_else)
    tx, _ = feed.process_sepay(db, _tx(77, memo))

    assert tx.status == "needs_review" and "Could not confirm" in tx.reason
    assert db.query(PaymentTransaction).count() == 1              # paid once, not twice


def test_split_bill_is_settled_by_the_bank_transfer_part(db, cashier):
    table = BilliardTable(name="T2", hourly_rate=D("310000"), client_id=CLIENT)
    db.add(table)
    db.flush()
    start = datetime.now(timezone.utc) - timedelta(hours=2)
    s = open_session(db, table, cashier.id, at=start)
    finalize_stop(db, s, table, cashier.id, at=start + timedelta(minutes=60))
    db.commit()
    sid = s.id
    session, _ = svc.pay_session(db, sid, PaySessionRequest(payments=[
        {"method": "cash", "amount": 200000}, {"method": "bank_transfer", "amount": 110000}]), cashier)
    transfer = session_service.build_bill(session)["payments"][1]

    tx, _ = feed.process_sepay(db, _tx(7, transfer["transfer"]["memo"], amount=110000))

    assert tx.status == "matched"
    assert _bill(db, cashier, sid)["payment_state"] == "paid"


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


def test_manager_assigns_an_unmatched_transfer_to_a_line(db, cashier, manager):
    sid, line = _transfer_line(db, cashier)
    tx, _ = feed.process_sepay(db, _tx(1, "", content="chuyen tien ban 1"))
    assert tx.status == "unmatched"
    assert [t.id for t in feed.list_transactions(db, manager, "unmatched")] == [tx.id]

    done = feed.assign(db, tx.id, line["id"], manager)

    assert done.status == "matched" and done.handled_by_id == manager.id and done.line_id == line["id"]
    assert _bill(db, cashier, sid)["payment_state"] == "paid"
    assert "transfer_assigned_from_bank" in _events(db, sid)
    with pytest.raises(HTTPException) as e:                      # cannot be assigned twice
        feed.assign(db, tx.id, line["id"], manager)
    assert e.value.status_code == 409


def test_assign_requires_the_exact_amount(db, cashier, manager):
    sid, line = _transfer_line(db, cashier)
    tx, _ = feed.process_sepay(db, _tx(1, "", content="x", transferAmount=300000))
    with pytest.raises(HTTPException) as e:
        feed.assign(db, tx.id, line["id"], manager)
    assert e.value.status_code == 422
    assert _bill(db, cashier, sid)["payment_state"] == "pending"


def test_manager_can_ignore_with_a_note(db, cashier, manager):
    _transfer_line(db, cashier)
    tx, _ = feed.process_sepay(db, _tx(1, "BIDA9L9", amount=50000))
    done = feed.ignore(db, tx.id, manager, "refunded to customer")
    assert done.status == "ignored" and done.note == "refunded to customer" and done.handled_by_id == manager.id


def test_other_clubs_manager_cannot_touch_a_matched_transaction(db, cashier):
    sid, line = _transfer_line(db, cashier)
    tx, _ = feed.process_sepay(db, _tx(1, line["transfer"]["memo"], amount=1))   # needs_review, scoped to c1
    rival = _user(db, "rival", role="manager", client="other")
    assert feed.list_transactions(db, rival) == []
    with pytest.raises(HTTPException) as e:
        feed.ignore(db, tx.id, rival, None)
    assert e.value.status_code == 404


# ---------------------------------------------------------------------- HTTP

@pytest.fixture()
def client(engine, db, monkeypatch):
    Session = sessionmaker(bind=engine, autoflush=False)
    app = FastAPI()
    app.include_router(bank_feed_router)
    app.dependency_overrides[get_db] = lambda: Session()
    return TestClient(app)


def test_webhook_http_api_key_flow(client, db, cashier, monkeypatch):
    monkeypatch.setattr(config, "SEPAY_API_KEY", "k123")
    sid, line = _transfer_line(db, cashier)
    payload = _tx(42, line["transfer"]["memo"])

    assert client.post("/bank-feed/sepay", json=payload).status_code == 401
    assert client.post("/bank-feed/sepay", json=payload, headers={"Authorization": "Apikey wrong"}).status_code == 401

    r = client.post("/bank-feed/sepay", json=payload, headers={"Authorization": "Apikey k123"})
    assert r.status_code == 200 and r.json() == {"success": True}
    r = client.post("/bank-feed/sepay", json=payload, headers={"Authorization": "Apikey k123"})   # SePay replay
    assert r.status_code == 200 and r.json() == {"success": True}

    db.expire_all()
    assert _bill(db, cashier, sid)["payment_state"] == "paid"
    assert db.query(BankTransaction).count() == 1


def test_webhook_http_hmac_uses_the_raw_body(client, db, cashier, monkeypatch):
    monkeypatch.setattr(config, "SEPAY_WEBHOOK_SECRET", "topsecret")
    sid, line = _transfer_line(db, cashier)
    body = json.dumps(_tx(43, line["transfer"]["memo"]), separators=(",", ":")).encode()
    ts = int(time.time())
    headers = {"Content-Type": "application/json", "X-SePay-Timestamp": str(ts),
               "X-SePay-Signature": _sign("topsecret", body, ts)}

    assert client.post("/bank-feed/sepay", content=body, headers=headers).json() == {"success": True}
    bad = {**headers, "X-SePay-Signature": _sign("wrong", body, ts)}
    assert client.post("/bank-feed/sepay", content=body, headers=bad).status_code == 401


def test_webhook_closed_when_not_configured_and_400_on_garbage(client, monkeypatch):
    assert client.post("/bank-feed/sepay", json={"id": 1}).status_code == 503
    monkeypatch.setattr(config, "SEPAY_API_KEY", "k")
    h = {"Authorization": "Apikey k"}
    assert client.post("/bank-feed/sepay", content=b"not json", headers=h).status_code == 400
    assert client.post("/bank-feed/sepay", json={"content": "no id"}, headers=h).status_code == 400
