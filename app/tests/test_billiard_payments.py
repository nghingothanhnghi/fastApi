# app/tests/test_billiard_payments.py
# Cash (tendered/change), bank transfer (VietQR, manual confirm), split payments and audit trail.
import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

# app.database / app.core.config validate env at import time.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/billiard_test_import.db")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
import app.billiard.models  # noqa: F401  (registers billiard tables)
from app.billiard import config
from app.billiard.models import BilliardTable, PaymentState, SessionPaymentEvent
from app.billiard.schemas.session import PaySessionRequest
from app.billiard.services.payment_service import billiard_payment_service as svc
from app.billiard.services.session_lifecycle import finalize_stop, open_session
from app.billiard.services.session_service import session_service
from app.billiard.utils import vietqr
from app.payments.models.payment import PaymentTransaction, PaymentStatus
from app.product.models.product import Product, ProductVariant  # noqa: F401  (session_items FK)
from app.user.models.user import User
from app.user.models.role import Role  # noqa: F401
from app.user.models.user_role import UserRole  # noqa: F401
from app.hydro_system.models.device import HydroDevice  # noqa: F401
from app.hydro_system.models.actuator import HydroActuator  # noqa: F401
from app.hydro_system.models.actuator_log import HydroActuatorLog  # noqa: F401
from app.hydro_system.models.schedule import HydroSchedule  # noqa: F401

CLIENT = "c1"


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, autoflush=False)()
    yield s
    s.close()


@pytest.fixture()
def user(db):
    u = User(client_id=CLIENT, username="cashier", email="c@x.com", hashed_password="x")
    db.add(u)
    db.commit()
    return u


@pytest.fixture()
def bank(monkeypatch):
    monkeypatch.setattr(config, "BANK_BIN", "970436")
    monkeypatch.setattr(config, "BANK_CODE", "VCB")
    monkeypatch.setattr(config, "BANK_ACCOUNT_NO", "0123456789")
    monkeypatch.setattr(config, "BANK_ACCOUNT_NAME", "BIDA CLUB")


def _bill(db, user, rate="310000"):
    """A stopped (completed) 1-hour session: grand_total == rate."""
    table = BilliardTable(name="T1", hourly_rate=Decimal(rate), client_id=CLIENT)
    db.add(table)
    db.flush()
    start = datetime.now(timezone.utc) - timedelta(hours=2)
    s = open_session(db, table, user.id, at=start)
    finalize_stop(db, s, table, user.id, at=start + timedelta(minutes=60))
    db.commit()
    return s.id


def _pay(db, user, session_id, **body):
    return svc.pay_session(db, session_id, PaySessionRequest(**body), user)


def _events(db, session_id):
    return [e.event_type for e in db.query(SessionPaymentEvent)
            .filter(SessionPaymentEvent.session_id == session_id).order_by(SessionPaymentEvent.id)]


# ------------------------------------------------------------------ VietQR

def test_crc16_ccitt_known_vector():
    assert vietqr.crc16_ccitt("123456789") == "29B1"


def _parse_tlv(s):
    out, i = {}, 0
    while i < len(s):
        tag, n = s[i:i + 2], int(s[i + 2:i + 4])
        out[tag] = s[i + 4:i + 4 + n]
        i += 4 + n
    return out


def test_vietqr_payload_structure_and_crc():
    payload = vietqr.build_payload("970436", "0123456789", Decimal("310000"), "BIDA42L7")

    assert payload[-8:-4] == "6304"
    assert vietqr.crc16_ccitt(payload[:-4]) == payload[-4:]
    top = _parse_tlv(payload)
    assert top["01"] == "12" and top["53"] == "704" and top["54"] == "310000" and top["58"] == "VN"
    assert _parse_tlv(top["62"])["08"] == "BIDA42L7"
    merchant = _parse_tlv(top["38"])
    assert merchant["00"] == "A000000727" and merchant["02"] == "QRIBFTTA"
    assert _parse_tlv(merchant["01"]) == {"00": "970436", "01": "0123456789"}


@pytest.mark.parametrize("amount,memo", [(Decimal("0"), "BIDA1L1"), (Decimal("1000"), "bad memo!")])
def test_vietqr_rejects_bad_input(amount, memo):
    with pytest.raises(ValueError):
        vietqr.build_payload("970436", "1", amount, memo)


# ------------------------------------------------------------ request schema

def test_request_needs_exactly_one_style():
    with pytest.raises(ValidationError):
        PaySessionRequest()
    with pytest.raises(ValidationError):
        PaySessionRequest(payment_method="cash", payments=[{"method": "cash", "amount": 1}])
    with pytest.raises(ValidationError):
        PaySessionRequest(payment_method="bank_transfer", cash_tendered=500000)
    with pytest.raises(ValidationError):
        PaySessionRequest(payments=[{"method": "bank_transfer", "amount": 1, "cash_tendered": 5}])


# --------------------------------------------------------------------- cash

def test_cash_with_tendered_gives_change_and_marks_paid(db, user):
    sid = _bill(db, user)

    session, gateway = _pay(db, user, sid, payment_method="cash", cash_tendered=500000)
    bill = session_service.build_bill(session)

    assert gateway is None
    assert bill["payment_state"] == "paid" and bill["payment_method"] == "cash"
    assert bill["amount_paid"] == Decimal("310000") and bill["balance_due"] == 0
    (line,) = bill["payments"]
    assert line["cash_tendered"] == Decimal("500000") and line["change_given"] == Decimal("190000")
    assert line["status"] == "completed" and line["payment_reference"]
    assert _events(db, sid) == ["line_created", "cash_received", "session_paid"]
    # the Payments module is still the source of truth
    tx = db.query(PaymentTransaction).one()
    assert tx.provider == "manual" and tx.status == PaymentStatus.COMPLETED and tx.amount == 310000


def test_cash_without_tendered_is_exact_amount(db, user):
    sid = _bill(db, user)
    session, _ = _pay(db, user, sid, payment_method="cash")
    (line,) = session_service.build_bill(session)["payments"]
    assert line["cash_tendered"] == Decimal("310000") and line["change_given"] == 0


def test_cash_tendered_below_amount_is_rejected_and_nothing_recorded(db, user):
    sid = _bill(db, user)
    with pytest.raises(HTTPException) as e:
        _pay(db, user, sid, payment_method="cash", cash_tendered=100000)
    assert e.value.status_code == 422
    bill = session_service.build_bill(session_service.get_session(db, sid, user))
    assert bill["payment_state"] == "unpaid" and bill["payments"] == []


def test_paying_twice_is_rejected(db, user):
    sid = _bill(db, user)
    _pay(db, user, sid, payment_method="cash")
    with pytest.raises(HTTPException) as e:
        _pay(db, user, sid, payment_method="cash")
    assert e.value.status_code == 409


# ----------------------------------------------------------------- transfer

def test_transfer_stays_pending_with_qr_until_cashier_confirms(db, user, bank):
    sid = _bill(db, user)

    session, _ = _pay(db, user, sid, payment_method="bank_transfer")
    bill = session_service.build_bill(session)

    assert bill["payment_state"] == "pending" and bill["amount_paid"] == 0
    assert bill["balance_due"] == Decimal("310000")
    (line,) = bill["payments"]
    assert line["status"] == "pending"
    t = line["transfer"]
    assert t["memo"] == f"BIDA{sid}L{line['id']}" and t["amount"] == Decimal("310000")
    assert t["qr_payload"] and vietqr.crc16_ccitt(t["qr_payload"][:-4]) == t["qr_payload"][-4:]
    assert "VCB-0123456789" in t["qr_image_url"] and "amount=310000" in t["qr_image_url"]
    assert t["expires_at"] is not None

    session = svc.confirm_transfer(db, sid, line["id"], user, note="saw it on the app")
    bill = session_service.build_bill(session)
    assert bill["payment_state"] == "paid" and bill["payment_method"] == "bank_transfer"
    assert bill["payments"][0]["transfer"] is None            # no QR once settled
    assert db.query(PaymentTransaction).one().status == PaymentStatus.COMPLETED
    assert _events(db, sid) == ["line_created", "transfer_awaiting", "transfer_confirmed", "session_paid"]


def test_transfer_without_bank_configured_has_no_qr(db, user, monkeypatch):
    monkeypatch.setattr(config, "BANK_BIN", "")
    sid = _bill(db, user)
    session, _ = _pay(db, user, sid, payment_method="bank_transfer")
    t = session_service.build_bill(session)["payments"][0]["transfer"]
    assert t["qr_payload"] is None and t["memo"]


def test_transfer_auto_confirm_switch_keeps_old_behaviour(db, user, monkeypatch):
    monkeypatch.setattr(config, "BANK_TRANSFER_REQUIRES_CONFIRMATION", False)
    sid = _bill(db, user)
    session, _ = _pay(db, user, sid, payment_method="bank_transfer")
    assert session_service.build_bill(session)["payment_state"] == "paid"


def test_confirm_transfer_is_idempotent_and_rejects_cash_lines(db, user):
    sid = _bill(db, user)
    s, _ = _pay(db, user, sid, payments=[
        {"method": "cash", "amount": 100000}, {"method": "bank_transfer", "amount": 210000}])
    cash, transfer = session_service.build_bill(s)["payments"]

    with pytest.raises(HTTPException) as e:
        svc.confirm_transfer(db, sid, cash["id"], user)
    assert e.value.status_code == 409

    svc.confirm_transfer(db, sid, transfer["id"], user)
    svc.confirm_transfer(db, sid, transfer["id"], user)       # second tick is a no-op
    assert db.query(PaymentTransaction).filter_by(status=PaymentStatus.COMPLETED).count() == 2
    with pytest.raises(HTTPException) as e:
        svc.confirm_transfer(db, sid, 9999, user)
    assert e.value.status_code == 404


# -------------------------------------------------------------------- split

def test_split_cash_and_transfer(db, user, bank):
    sid = _bill(db, user)

    session, _ = _pay(db, user, sid, payments=[
        {"method": "cash", "amount": 200000, "cash_tendered": 200000},
        {"method": "bank_transfer", "amount": 110000},
    ])
    bill = session_service.build_bill(session)

    assert bill["payment_state"] == "pending" and bill["payment_method"] == "split"
    assert bill["amount_paid"] == Decimal("200000") and bill["balance_due"] == Decimal("110000")
    assert [p["status"] for p in bill["payments"]] == ["completed", "pending"]
    # a second /pay while the transfer is awaiting is blocked
    with pytest.raises(HTTPException) as e:
        _pay(db, user, sid, payment_method="cash")
    assert e.value.status_code == 409

    session = svc.confirm_transfer(db, sid, bill["payments"][1]["id"], user)
    bill = session_service.build_bill(session)
    assert bill["payment_state"] == "paid" and bill["amount_paid"] == Decimal("310000")
    assert bill["paid_at"] is not None


def test_split_that_does_not_add_up_is_rejected(db, user):
    sid = _bill(db, user)
    with pytest.raises(HTTPException) as e:
        _pay(db, user, sid, payments=[
            {"method": "cash", "amount": 100000}, {"method": "bank_transfer", "amount": 100000}])
    assert e.value.status_code == 422
    assert db.query(PaymentTransaction).count() == 0


def test_split_between_two_cash_lines_settles_immediately(db, user):
    sid = _bill(db, user)
    session, _ = _pay(db, user, sid, payments=[
        {"method": "cash", "amount": 10000}, {"method": "cash", "amount": 300000, "cash_tendered": 500000}])
    bill = session_service.build_bill(session)
    assert bill["payment_state"] == "paid"
    assert [p["change_given"] for p in bill["payments"]] == [Decimal("0"), Decimal("200000")]


def test_cancel_transfer_then_pay_the_balance_with_cash(db, user):
    sid = _bill(db, user)
    s, _ = _pay(db, user, sid, payments=[
        {"method": "cash", "amount": 200000}, {"method": "bank_transfer", "amount": 110000}])
    transfer = session_service.build_bill(s)["payments"][1]

    s = svc.cancel_line(db, sid, transfer["id"], user, reason="customer has no signal")
    bill = session_service.build_bill(s)
    assert bill["payment_state"] == "pending" and bill["balance_due"] == Decimal("110000")
    assert bill["payments"][1]["status"] == "cancelled"
    failed = db.query(PaymentTransaction).filter_by(status=PaymentStatus.FAILED).one()
    assert failed.extra_metadata["billiard_session_id"] == sid       # reconciliation info kept
    assert failed.extra_metadata["cancel_reason"] == "customer has no signal"

    # only the balance can be paid now
    with pytest.raises(HTTPException) as e:
        _pay(db, user, sid, payments=[{"method": "cash", "amount": 310000}])
    assert e.value.status_code == 422

    s, _ = _pay(db, user, sid, payment_method="cash", cash_tendered=200000)
    bill = session_service.build_bill(s)
    assert bill["payment_state"] == "paid" and bill["amount_paid"] == Decimal("310000")
    assert bill["payments"][2]["change_given"] == Decimal("90000")
    assert "line_cancelled" in _events(db, sid)


def test_cancelling_the_only_pending_line_releases_the_bill(db, user):
    sid = _bill(db, user)
    s, _ = _pay(db, user, sid, payment_method="bank_transfer")
    line = session_service.build_bill(s)["payments"][0]

    s = svc.cancel_line(db, sid, line["id"], user)

    assert session_service.build_bill(s)["payment_state"] == "unpaid"
    s, _ = _pay(db, user, sid, payment_method="cash")          # cashier can start over
    assert session_service.build_bill(s)["payment_state"] == "paid"


def test_cannot_cancel_a_completed_line(db, user):
    sid = _bill(db, user)
    s, _ = _pay(db, user, sid, payment_method="cash")
    line = session_service.build_bill(s)["payments"][0]
    with pytest.raises(HTTPException) as e:
        svc.cancel_line(db, sid, line["id"], user)
    assert e.value.status_code == 409


def test_payment_events_are_tenant_scoped(db, user):
    sid = _bill(db, user)
    _pay(db, user, sid, payment_method="cash")
    assert [e.event_type for e in svc.list_events(db, sid, user)][-1] == "session_paid"

    other = User(client_id="other", username="x", email="x@x.com", hashed_password="x")
    db.add(other)
    db.commit()
    with pytest.raises(HTTPException) as e:
        svc.list_events(db, sid, other)
    assert e.value.status_code == 404
