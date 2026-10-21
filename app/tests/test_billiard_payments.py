# app/tests/test_billiard_payments.py
# Billiard's side of payments only: the PayableAdapter (when a session may be paid, how much, which
# club), the state mirror on the session/bill, legacy sessions, and the URLs. Cash change, split,
# VietQR, bank feed, void and shifts are tested once, in the Payments module (test_payments_*.py).
import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

# app.database / app.core.config validate env at import time.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/billiard_test_import.db")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import app.billiard.models  # noqa: F401  (registers billiard tables)
from app.billiard.models import BilliardTable, PaymentState, SessionStatus, TableSession
from app.billiard.routes import billiard_router
from app.billiard.services.payment_service import billiard_payment_service as svc
from app.billiard.services.session_lifecycle import finalize_stop, open_session
from app.billiard.services.session_service import session_service
from app.database import get_db
from app.payments import config as pay_config
from app.payments.models.payment import PaymentTransaction
from app.payments.routes import bank_feed_router, order_router, payment_router, shift_router
from app.payments.schemas.order import PayOrderRequest
from app.payments.services.bank_feed_service import bank_feed_service as feed
from app.payments.services.payable_registry import payable_registry
from app.tests.payments_testkit import CLIENT, D, cashier, db, engine, make_user, manager  # noqa: F401
from app.user.utils.token import get_current_user


def _stopped_session(db, user, rate="310000", client=CLIENT):
    """A completed (stopped) 1-hour session: grand_total == rate."""
    table = BilliardTable(name=f"T{db.query(BilliardTable).count() + 1}", hourly_rate=D(rate), client_id=client)
    db.add(table)
    db.flush()
    start = datetime.now(timezone.utc) - timedelta(hours=2)
    s = open_session(db, table, user.id, at=start)
    finalize_stop(db, s, table, user.id, at=start + timedelta(minutes=60))
    db.commit()
    return s.id


def _pay(db, user, session_id, **body):
    return svc.pay_session(db, session_id, PayOrderRequest(**body), user)


def _bill(db, user, session_id):
    return session_service.build_bill(session_service.get_session(db, session_id, user))


@pytest.fixture(autouse=True)
def bank(monkeypatch):
    monkeypatch.setattr(pay_config, "BANK_BIN", "970436")
    monkeypatch.setattr(pay_config, "BANK_ACCOUNT_NO", "0123456789")
    monkeypatch.setattr(pay_config, "BANK_CODE", "VCB")


# ------------------------------------------------------------------ registration

def test_billiard_registers_itself_as_a_payable_business():
    assert payable_registry.get("billiard_session").source_type == "billiard_session"


# --------------------------------------------------------------- adapter rules

def test_only_a_stopped_session_can_be_paid(db, cashier):
    table = BilliardTable(name="T1", hourly_rate=D("310000"), client_id=CLIENT)
    db.add(table)
    db.flush()
    active = open_session(db, table, cashier.id)
    db.commit()

    with pytest.raises(HTTPException) as e:
        _pay(db, cashier, active.id, payment_method="cash")
    assert e.value.status_code == 409 and "Stop the session" in e.value.detail
    assert db.query(PaymentTransaction).count() == 0


def test_other_clubs_get_404_not_403(db, cashier):
    sid = _stopped_session(db, cashier)
    stranger = make_user(db, "stranger", client="other")
    with pytest.raises(HTTPException) as e:
        _pay(db, stranger, sid, payment_method="cash")
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        svc.list_events(db, sid, stranger)
    assert e.value.status_code == 404


def test_amount_always_comes_from_the_session_total(db, cashier):
    sid = _stopped_session(db, cashier, rate="250000")
    _pay(db, cashier, sid, payment_method="cash")
    tx = db.query(PaymentTransaction).one()
    assert tx.amount == 250000 and tx.currency == "VND"
    assert tx.client_id == CLIENT


def test_payment_metadata_lets_a_human_reconcile_with_the_session(db, cashier):
    sid = _stopped_session(db, cashier)
    _pay(db, cashier, sid, payment_method="cash")
    meta = db.query(PaymentTransaction).one().extra_metadata
    assert meta["billiard_session_id"] == sid and meta["table"] and meta["payment_order_id"]


# ---------------------------------------------------- the mirror on the session

def test_cash_payment_is_mirrored_onto_the_session_and_the_bill(db, cashier):
    sid = _stopped_session(db, cashier)

    session, gateway = _pay(db, cashier, sid, payment_method="cash", cash_tendered=500000)
    bill = session_service.build_bill(session)

    assert gateway is None
    assert session.payment_state == PaymentState.PAID and session.payment_method == "cash"
    assert session.payment_order_id and session.payment_id and session.payment_reference
    assert session.paid_at is not None and session.paid_by_id == cashier.id
    assert bill["payment_state"] == "paid" and bill["paid_by"] == "cashier"
    assert bill["amount_paid"] == D("310000") and bill["balance_due"] == 0
    (line,) = bill["payments"]
    assert line["cash_tendered"] == D("500000") and line["change_given"] == D("190000")
    # reports filter on the mirror without joining the Payments tables
    assert db.query(TableSession).filter(TableSession.payment_state == PaymentState.PAID).count() == 1


def test_transfer_waits_with_a_qr_then_the_cashier_confirms(db, cashier):
    sid = _stopped_session(db, cashier)

    session, _ = _pay(db, cashier, sid, payment_method="bank_transfer")
    bill = session_service.build_bill(session)

    assert session.payment_state == PaymentState.PENDING and session.paid_at is None
    assert bill["balance_due"] == D("310000")
    line = bill["payments"][0]
    assert line["transfer"]["memo"].startswith(pay_config.MEMO_PREFIX) and line["transfer"]["qr_payload"]

    session = svc.confirm_transfer(db, sid, line["id"], cashier)
    assert session.payment_state == PaymentState.PAID and session.payment_method == "bank_transfer"


def test_split_payment_shows_both_lines_and_settles_when_complete(db, cashier):
    sid = _stopped_session(db, cashier)
    session, _ = _pay(db, cashier, sid, payments=[
        {"method": "cash", "amount": 200000}, {"method": "bank_transfer", "amount": 110000}])
    bill = session_service.build_bill(session)

    assert session.payment_state == PaymentState.PENDING and session.payment_method == "split"
    assert bill["amount_paid"] == D("200000") and bill["balance_due"] == D("110000")
    assert [p["status"] for p in bill["payments"]] == ["completed", "pending"]

    session = svc.confirm_transfer(db, sid, bill["payments"][1]["id"], cashier)
    assert session.payment_state == PaymentState.PAID


def test_bank_feed_settles_the_session_without_a_person(db, cashier):
    sid = _stopped_session(db, cashier)
    session, _ = _pay(db, cashier, sid, payment_method="bank_transfer")
    memo = session_service.build_bill(session)["payments"][0]["transfer"]["memo"]

    tx, _ = feed.process_sepay(db, {
        "id": 555, "transferType": "in", "transferAmount": 310000, "accountNumber": "0123456789",
        "content": f"thanh toan {memo}", "gateway": "Vietcombank",
    })

    assert tx.status == "matched"
    db.expire_all()
    session = session_service.get_session(db, sid, cashier)
    assert session.payment_state == PaymentState.PAID and session.paid_by_id is None


def test_manager_void_reopens_the_session(db, cashier, manager):
    sid = _stopped_session(db, cashier)
    session, _ = _pay(db, cashier, sid, payment_method="cash")
    line_id = session_service.build_bill(session)["payments"][0]["id"]

    with pytest.raises(HTTPException) as e:
        svc.void_line(db, sid, line_id, cashier, "oops")
    assert e.value.status_code == 403 and session_service.get_session(db, sid, cashier).payment_state == PaymentState.PAID

    session = svc.void_line(db, sid, line_id, manager, "wrong table charged")
    bill = session_service.build_bill(session)

    assert session.payment_state == PaymentState.UNPAID and session.paid_at is None and session.paid_by_id is None
    assert bill["balance_due"] == D("310000") and bill["payments"][0]["status"] == "voided"
    _pay(db, cashier, sid, payment_method="cash")                          # can be paid again
    assert session_service.get_session(db, sid, cashier).payment_state == PaymentState.PAID


def test_failed_transfer_cancel_releases_the_session(db, cashier):
    sid = _stopped_session(db, cashier)
    session, _ = _pay(db, cashier, sid, payment_method="bank_transfer")
    session = svc.cancel_line(db, sid, session_service.build_bill(session)["payments"][0]["id"], cashier, "no signal")
    assert session.payment_state == PaymentState.UNPAID and session.payment_method is None


# --------------------------------------------------------------------- Stripe

def _intent(status):
    return SimpleNamespace(id="pi_1", client_secret="sec", status=status)


def test_stripe_pending_then_confirmed(db, cashier):
    sid = _stopped_session(db, cashier)
    with patch("stripe.PaymentIntent.create", return_value=_intent("requires_payment_method")):
        session, gateway = _pay(db, cashier, sid, payment_method="stripe")
    assert gateway["client_secret"] == "sec" and session.payment_state == PaymentState.PENDING
    assert session.payment_method == "stripe"

    with patch("stripe.PaymentIntent.retrieve", return_value=_intent("succeeded")):
        session = svc.confirm_payment(db, sid, cashier)
    assert session.payment_state == PaymentState.PAID


# ------------------------------------------------------------ sessions before the module

def test_session_paid_before_the_payments_module_stays_paid(db, cashier):
    """Demo/legacy rows: paid, but never had an order."""
    sid = _stopped_session(db, cashier)
    session = session_service.get_session(db, sid, cashier)
    session.payment_state, session.payment_method, session.paid_at = PaymentState.PAID, "cash", datetime.now(timezone.utc)
    db.commit()

    bill = _bill(db, cashier, sid)
    assert bill["payment_state"] == "paid" and bill["amount_paid"] == D("310000") and bill["payments"] == []
    with pytest.raises(HTTPException) as e:
        _pay(db, cashier, sid, payment_method="cash")
    assert e.value.status_code == 409
    assert svc.confirm_payment(db, sid, cashier).payment_state == PaymentState.PAID
    assert svc.list_events(db, sid, cashier) == []


def test_confirm_without_any_gateway_payment_is_a_409(db, cashier):
    sid = _stopped_session(db, cashier)
    with pytest.raises(HTTPException) as e:
        svc.confirm_payment(db, sid, cashier)
    assert e.value.status_code == 409


# ------------------------------------------------------------------------ HTTP

@pytest.fixture()
def http(engine, db, cashier, manager):
    """The app wired like main.py: legacy payment_router first, then the Payments routers, then billiard."""
    Session = sessionmaker(bind=engine, autoflush=False)
    app = FastAPI()
    app.include_router(payment_router.router)
    app.include_router(order_router.router)
    app.include_router(shift_router.router)
    app.include_router(bank_feed_router.router)
    app.include_router(billiard_router)
    app.dependency_overrides[get_db] = lambda: Session()
    current = {"id": cashier.id}
    app.dependency_overrides[get_current_user] = lambda: db.get(type(cashier), current["id"])
    client = TestClient(app)
    client.as_user = lambda u: current.update(id=u.id)
    return client


def test_billiard_urls_and_payments_urls_are_the_same_operation(http, db, cashier):
    s1, s2 = _stopped_session(db, cashier), _stopped_session(db, cashier)

    r = http.post(f"/sessions/{s1}/pay", json={"payments": [
        {"method": "cash", "amount": 200000, "cash_tendered": 250000}, {"method": "bank_transfer", "amount": 110000}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["payment_state"] == "pending" and body["balance_due"] == "110000.00" and body["gateway"] is None
    assert [(p["method"], p["status"], p["change_given"]) for p in body["payments"]] == \
        [("cash", "completed", "50000.00"), ("bank_transfer", "pending", None)]

    # the generic Payments API sees the very same bill...
    g = http.get(f"/payments/orders/billiard_session/{s1}")
    assert g.status_code == 200 and g.json()["balance_due"] == "110000.00" and g.json()["state"] == "pending"
    # ...and can take payment for another session, mirrored back onto it
    r = http.post(f"/payments/orders/billiard_session/{s2}/pay", json={"payment_method": "cash"})
    assert r.status_code == 200 and r.json()["state"] == "paid"
    assert http.get(f"/sessions/{s2}").json()["payment_state"] == "paid"

    line_id = body["payments"][1]["id"]
    assert http.post(f"/sessions/{s1}/pay/lines/{line_id}/confirm").json()["payment_state"] == "paid"
    events = [e["event_type"] for e in http.get(f"/sessions/{s1}/pay/events").json()]
    assert events[-1] == "order_paid" and "transfer_confirmed" in events


def test_void_is_manager_only_over_http_on_both_urls(http, db, cashier, manager):
    sid = _stopped_session(db, cashier)
    line_id = http.post(f"/sessions/{sid}/pay", json={"payment_method": "cash"}).json()["payments"][0]["id"]

    assert http.post(f"/sessions/{sid}/pay/lines/{line_id}/void", json={"reason": "wrong table"}).status_code == 403
    assert http.post(f"/payments/orders/billiard_session/{sid}/lines/{line_id}/void",
                     json={"reason": "wrong table"}).status_code == 403

    http.as_user(manager)
    r = http.post(f"/sessions/{sid}/pay/lines/{line_id}/void", json={"reason": "wrong table"})
    assert r.status_code == 200 and r.json()["payment_state"] == "unpaid"


def test_routes_do_not_collide_with_the_legacy_payments_router(http, db, cashier):
    assert http.get("/payments/shifts/current").status_code == 200
    assert http.get("/payments/shifts").status_code == 200
    assert http.get("/payments/orders/billiard_session/999999").status_code == 404
    assert http.get("/payments/orders/unknown_type/1").status_code == 404
    r = http.post("/payments/shifts/open", json={"opening_float": 500000})
    assert r.status_code == 201 and r.json()["expected_cash"] == "500000.00"


def test_validation_errors_over_http(http, db, cashier):
    sid = _stopped_session(db, cashier)
    assert http.post(f"/sessions/{sid}/pay", json={}).status_code == 422
    assert http.post(f"/sessions/{sid}/pay", json={"payments": [
        {"method": "cash", "amount": 1}, {"method": "bank_transfer", "amount": 2}]}).status_code == 422
    assert http.post("/sessions/999999/pay", json={"payment_method": "cash"}).status_code == 404
