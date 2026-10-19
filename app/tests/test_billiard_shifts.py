# app/tests/test_billiard_shifts.py
# Shifts, cash drawer maths (expected / counted / variance), pay-in/out and manager-only voids.
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
from app.billiard.schemas.shift import CashMovementRequest
from app.billiard.services.payment_service import billiard_payment_service as svc
from app.billiard.services.session_lifecycle import finalize_stop, open_session
from app.billiard.services.session_service import session_service
from app.billiard.services.shift_service import shift_service as shifts
from app.payments.models.payment import PaymentTransaction, PaymentStatus
from app.product.models.product import Product, ProductVariant  # noqa: F401  (session_items FK)
from app.user.models.user import User
from app.user.models.role import Role
from app.user.models.user_role import UserRole
from app.hydro_system.models.device import HydroDevice  # noqa: F401
from app.hydro_system.models.actuator import HydroActuator  # noqa: F401
from app.hydro_system.models.actuator_log import HydroActuatorLog  # noqa: F401
from app.hydro_system.models.schedule import HydroSchedule  # noqa: F401

CLIENT = "c1"
D = Decimal


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, autoflush=False)()
    yield s
    s.close()


def _user(db, name, role=None, client=CLIENT):
    u = User(client_id=client, username=name, email=f"{name}@x.com", hashed_password="x")
    db.add(u)
    db.flush()
    if role:
        r = db.query(Role).filter_by(name=role).first()
        if not r:
            r = Role(name=role, display_name=role, is_active=True)
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


_table_seq = iter(range(1000))


def _bill(db, user, rate="310000"):
    """A stopped (completed) 1-hour session: grand_total == rate."""
    table = BilliardTable(name=f"T{next(_table_seq)}", hourly_rate=D(rate), client_id=user.client_id)
    db.add(table)
    db.flush()
    start = datetime.now(timezone.utc) - timedelta(hours=2)
    s = open_session(db, table, user.id, at=start)
    finalize_stop(db, s, table, user.id, at=start + timedelta(minutes=60))
    db.commit()
    return s.id


def _pay(db, user, session_id, **body):
    return svc.pay_session(db, session_id, PaySessionRequest(**body), user)


def _open(db, user, float_="1000000"):
    shift = shifts.open_shift(db, user, D(float_), None)
    db.commit()
    return shift.id


def _summary(db, user, shift_id):
    return shifts.summary(db, shifts.get_shift(db, shift_id, user))


# ------------------------------------------------------------------ lifecycle

def test_open_shift_and_only_one_per_club(db, cashier):
    sid = _open(db, cashier, "500000")
    s = _summary(db, cashier, sid)
    assert s.status == "open" and s.opening_float == D("500000") and s.expected_cash == D("500000")
    assert s.opened_by == "cashier"

    with pytest.raises(HTTPException) as e:
        shifts.open_shift(db, cashier, D("0"), None)
    assert e.value.status_code == 409
    assert shifts.get_open_shift(db, CLIENT).id == sid


def test_other_club_can_open_its_own_shift(db, cashier):
    _open(db, cashier)
    other = _user(db, "other", client="c2")
    assert shifts.open_shift(db, other, D("0"), None).client_id == "c2"


def test_expected_cash_follows_cash_sales_net_of_change(db, cashier):
    shift_id = _open(db, cashier, "1000000")
    sid = _bill(db, cashier)

    _pay(db, cashier, sid, payment_method="cash", cash_tendered=500000)   # change 190000

    s = _summary(db, cashier, shift_id)
    assert s.cash_sales == D("310000") and s.change_given == D("190000")
    assert s.expected_cash == D("1310000")                                # change is not in the drawer
    assert s.payments_count == 1
    assert [(m.method, m.received_total) for m in s.methods] == [("cash", D("310000"))]


def test_transfer_is_reported_but_not_counted_as_drawer_cash(db, cashier):
    shift_id = _open(db, cashier, "0")
    sid = _bill(db, cashier)
    s, _ = _pay(db, cashier, sid, payment_method="bank_transfer")
    line = session_service.build_bill(s)["payments"][0]

    assert _summary(db, cashier, shift_id).payments_count == 0            # still pending
    svc.confirm_transfer(db, sid, line["id"], cashier)

    summary = _summary(db, cashier, shift_id)
    assert summary.expected_cash == D("0") and summary.cash_sales == 0
    assert [(m.method, m.net_total) for m in summary.methods] == [("bank_transfer", D("310000"))]


def test_pay_in_and_pay_out_adjust_expected_cash(db, cashier):
    shift_id = _open(db, cashier, "100000")
    shifts.add_movement(db, shift_id, cashier, "pay_in", D("50000"), "change from the safe")
    shifts.add_movement(db, shift_id, cashier, "pay_out", D("30000"), "bought ice")
    db.commit()

    s = _summary(db, cashier, shift_id)
    assert (s.pay_ins, s.pay_outs, s.expected_cash) == (D("50000"), D("30000"), D("120000"))
    assert [m.reason for m in s.movements] == ["change from the safe", "bought ice"]
    assert s.movements[0].created_by == "cashier"


def test_pay_out_cannot_exceed_cash_in_drawer(db, cashier):
    shift_id = _open(db, cashier, "100000")
    with pytest.raises(HTTPException) as e:
        shifts.add_movement(db, shift_id, cashier, "pay_out", D("100001"), "too much")
    assert e.value.status_code == 409


def test_movement_request_needs_a_reason_and_positive_amount():
    with pytest.raises(ValidationError):
        CashMovementRequest(type="pay_out", amount=1000, reason="")
    with pytest.raises(ValidationError):
        CashMovementRequest(type="pay_in", amount=0, reason="float top up")


def test_close_shift_records_variance_and_freezes_the_numbers(db, cashier):
    shift_id = _open(db, cashier, "1000000")
    sid = _bill(db, cashier)
    _pay(db, cashier, sid, payment_method="cash")

    shifts.close_shift(db, shift_id, cashier, D("1300000"), "10k short")
    db.commit()

    s = _summary(db, cashier, shift_id)
    assert s.status == "closed" and s.closed_by == "cashier" and s.closed_at is not None
    assert (s.expected_cash, s.counted_cash, s.variance) == (D("1310000"), D("1300000"), D("-10000"))
    assert s.close_note == "10k short"
    assert shifts.get_open_shift(db, CLIENT) is None

    # a payment after close is not added to the closed shift
    _pay(db, cashier, _bill(db, cashier), payment_method="cash")
    assert _summary(db, cashier, shift_id).expected_cash == D("1310000")

    with pytest.raises(HTTPException) as e:
        shifts.close_shift(db, shift_id, cashier, D("0"), None)
    assert e.value.status_code == 409
    with pytest.raises(HTTPException) as e:
        shifts.add_movement(db, shift_id, cashier, "pay_in", D("1000"), "late")
    assert e.value.status_code == 409


def test_close_after_reloading_from_the_database_with_movements(db, cashier):
    shift_id = _open(db, cashier, "100000")
    shifts.add_movement(db, shift_id, cashier, "pay_out", D("30000"), "bought ice")
    db.commit()
    db.expire_all()                                   # force a fresh load (naive datetimes on SQLite)

    shifts.close_shift(db, shift_id, cashier, D("70000"), None)
    db.commit()

    s = _summary(db, cashier, shift_id)
    assert (s.expected_cash, s.variance, s.pay_outs) == (D("70000"), D("0"), D("30000"))


def test_only_opener_or_manager_can_close(db, cashier, manager):
    shift_id = _open(db, cashier)
    other = _user(db, "other_cashier")
    with pytest.raises(HTTPException) as e:
        shifts.close_shift(db, shift_id, other, D("1000000"), None)
    assert e.value.status_code == 403
    assert shifts.close_shift(db, shift_id, manager, D("1000000"), None).closed_by_id == manager.id


def test_shifts_are_tenant_scoped(db, cashier):
    shift_id = _open(db, cashier)
    other = _user(db, "other", client="c2")
    with pytest.raises(HTTPException) as e:
        shifts.get_shift(db, shift_id, other)
    assert e.value.status_code == 404
    assert shifts.list_shifts(db, other) == [] and len(shifts.list_shifts(db, cashier)) == 1


def test_require_open_shift_flag_gates_payments(db, cashier, monkeypatch):
    monkeypatch.setattr(config, "REQUIRE_OPEN_SHIFT", True)
    sid = _bill(db, cashier)
    with pytest.raises(HTTPException) as e:
        _pay(db, cashier, sid, payment_method="cash")
    assert e.value.status_code == 409 and "shift" in e.value.detail.lower()

    _open(db, cashier)
    s, _ = _pay(db, cashier, sid, payment_method="cash")
    assert s.payment_state == PaymentState.PAID


def test_payments_allowed_without_shift_by_default(db, cashier):
    s, _ = _pay(db, cashier, _bill(db, cashier), payment_method="cash")
    assert s.payment_state == PaymentState.PAID


# ---------------------------------------------------------------------- void

def test_only_a_manager_can_void(db, cashier, manager):
    sid = _bill(db, cashier)
    s, _ = _pay(db, cashier, sid, payment_method="cash")
    line = session_service.build_bill(s)["payments"][0]

    with pytest.raises(HTTPException) as e:
        svc.void_line(db, sid, line["id"], cashier, "customer changed mind")
    assert e.value.status_code == 403
    assert session_service.get_session(db, sid, cashier).payment_state == PaymentState.PAID


def test_void_requires_a_reason(db, cashier, manager):
    sid = _bill(db, cashier)
    s, _ = _pay(db, cashier, sid, payment_method="cash")
    line = session_service.build_bill(s)["payments"][0]
    for bad in ("", "  ", "x"):
        with pytest.raises(HTTPException) as e:
            svc.void_line(db, sid, line["id"], manager, bad)
        assert e.value.status_code == 422


def test_void_reopens_the_bill_refunds_the_payment_and_is_audited(db, cashier, manager):
    sid = _bill(db, cashier)
    s, _ = _pay(db, cashier, sid, payment_method="cash")
    line = session_service.build_bill(s)["payments"][0]

    s = svc.void_line(db, sid, line["id"], manager, "wrong table charged")
    bill = session_service.build_bill(s)

    assert bill["payment_state"] == "unpaid" and bill["paid_at"] is None and bill["paid_by"] is None
    assert bill["amount_paid"] == 0 and bill["balance_due"] == D("310000")
    v = bill["payments"][0]
    assert v["status"] == "voided" and v["void_reason"] == "wrong table charged" and v["voided_at"]
    assert db.query(PaymentTransaction).one().status == PaymentStatus.REFUNDED
    events = [e.event_type for e in db.query(SessionPaymentEvent).filter_by(session_id=sid).order_by(SessionPaymentEvent.id)]
    assert events[-1] == "line_voided"
    voided = db.query(SessionPaymentEvent).filter_by(event_type="line_voided").one()
    assert voided.actor_id == manager.id and voided.data["reason"] == "wrong table charged"

    # the cashier can take the money again
    s, _ = _pay(db, cashier, sid, payment_method="cash")
    assert session_service.build_bill(s)["payment_state"] == "paid"
    with pytest.raises(HTTPException) as e:                       # a voided line can't be voided twice
        svc.void_line(db, sid, line["id"], manager, "again")
    assert e.value.status_code == 409


def test_voiding_one_line_of_a_split_leaves_the_bill_part_paid(db, cashier, manager):
    sid = _bill(db, cashier)
    s, _ = _pay(db, cashier, sid, payments=[
        {"method": "cash", "amount": 100000}, {"method": "cash", "amount": 210000}])
    first = session_service.build_bill(s)["payments"][0]

    s = svc.void_line(db, sid, first["id"], manager, "gave too much")
    bill = session_service.build_bill(s)

    assert bill["payment_state"] == "pending" and bill["amount_paid"] == D("210000")
    assert bill["balance_due"] == D("100000")


def test_cannot_void_a_pending_line(db, cashier, manager):
    sid = _bill(db, cashier)
    s, _ = _pay(db, cashier, sid, payment_method="bank_transfer")
    line = session_service.build_bill(s)["payments"][0]
    with pytest.raises(HTTPException) as e:
        svc.void_line(db, sid, line["id"], manager, "not paid yet")
    assert e.value.status_code == 409


def test_cash_void_in_the_same_shift_nets_to_zero(db, cashier, manager):
    shift_id = _open(db, cashier, "1000000")
    sid = _bill(db, cashier)
    s, _ = _pay(db, cashier, sid, payment_method="cash")
    svc.void_line(db, sid, session_service.build_bill(s)["payments"][0]["id"], manager, "mistake")

    s = _summary(db, cashier, shift_id)
    assert (s.cash_sales, s.cash_voids, s.expected_cash) == (D("310000"), D("310000"), D("1000000"))
    assert s.methods[0].net_total == 0


def test_cash_void_after_close_is_money_out_of_the_next_shift(db, cashier, manager):
    first = _open(db, cashier, "1000000")
    sid = _bill(db, cashier)
    s, _ = _pay(db, cashier, sid, payment_method="cash")
    line_id = session_service.build_bill(s)["payments"][0]["id"]
    shifts.close_shift(db, first, cashier, D("1310000"), None)
    db.commit()
    second = _open(db, cashier, "200000")

    svc.void_line(db, sid, line_id, manager, "refund next day")

    assert _summary(db, cashier, first).expected_cash == D("1310000")          # closed shift unchanged
    s2 = _summary(db, cashier, second)
    assert (s2.cash_sales, s2.cash_voids, s2.expected_cash) == (0, D("310000"), D("-110000"))
