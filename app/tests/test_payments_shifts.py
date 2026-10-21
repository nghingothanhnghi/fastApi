# app/tests/test_payments_shifts.py
# Cash drawer: shifts, expected cash / counted / variance, pay-in/out, and how voids hit the drawer.
# Runs against the FAKE business (payments_testkit); no billiard involved.
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.payments import config
from app.payments.schemas.shift import CashMovementRequest
from app.payments.services.order_service import payment_order_service as svc
from app.payments.services.shift_service import shift_service as shifts
from app.tests.payments_testkit import (  # noqa: F401  (fixtures are used by name)
    CLIENT, D, FAKE, cashier, db, engine, fake, make_user, manager, pay, view,
)


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
    other = make_user(db, "other", client="c2")
    assert shifts.open_shift(db, other, D("0"), None).client_id == "c2"


def test_expected_cash_follows_cash_sales_net_of_change(db, cashier, fake):
    shift_id = _open(db, cashier, "1000000")

    pay(db, cashier, fake.create(), payment_method="cash", cash_tendered=500000)   # change 190000

    s = _summary(db, cashier, shift_id)
    assert s.cash_sales == D("310000") and s.change_given == D("190000")
    assert s.expected_cash == D("1310000")                                       # change is not in the drawer
    assert s.payments_count == 1
    assert [(m.method, m.received_total) for m in s.methods] == [("cash", D("310000"))]


def test_transfer_is_reported_but_not_counted_as_drawer_cash(db, cashier, fake):
    shift_id = _open(db, cashier, "0")
    bill_id = fake.create()
    pay(db, cashier, bill_id, payment_method="bank_transfer")
    line = view(db, cashier, bill_id)["payments"][0]

    assert _summary(db, cashier, shift_id).payments_count == 0                   # still pending
    svc.confirm_transfer(db, FAKE, bill_id, line["id"], cashier)

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


def test_close_shift_records_variance_and_freezes_the_numbers(db, cashier, fake):
    shift_id = _open(db, cashier, "1000000")
    pay(db, cashier, fake.create(), payment_method="cash")

    shifts.close_shift(db, shift_id, cashier, D("1300000"), "10k short")
    db.commit()

    s = _summary(db, cashier, shift_id)
    assert s.status == "closed" and s.closed_by == "cashier" and s.closed_at is not None
    assert (s.expected_cash, s.counted_cash, s.variance) == (D("1310000"), D("1300000"), D("-10000"))
    assert s.close_note == "10k short" and shifts.get_open_shift(db, CLIENT) is None

    pay(db, cashier, fake.create(), payment_method="cash")                       # after close: not in this shift
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
    other = make_user(db, "other_cashier")
    with pytest.raises(HTTPException) as e:
        shifts.close_shift(db, shift_id, other, D("1000000"), None)
    assert e.value.status_code == 403
    assert shifts.close_shift(db, shift_id, manager, D("1000000"), None).closed_by_id == manager.id


def test_shifts_are_tenant_scoped(db, cashier):
    shift_id = _open(db, cashier)
    other = make_user(db, "other", client="c2")
    with pytest.raises(HTTPException) as e:
        shifts.get_shift(db, shift_id, other)
    assert e.value.status_code == 404
    assert shifts.list_shifts(db, other) == [] and len(shifts.list_shifts(db, cashier)) == 1


def test_drawer_only_counts_the_clubs_own_payments(db, cashier, fake):
    shift_id = _open(db, cashier, "0")
    other = make_user(db, "other", client="c2")
    pay(db, other, fake.create(client_id="c2"), payment_method="cash")           # another club's sale

    assert _summary(db, cashier, shift_id).cash_sales == 0


def test_require_open_shift_flag_gates_payments(db, cashier, fake, monkeypatch):
    monkeypatch.setattr(config, "REQUIRE_OPEN_SHIFT", True)
    bill_id = fake.create()
    with pytest.raises(HTTPException) as e:
        pay(db, cashier, bill_id, payment_method="cash")
    assert e.value.status_code == 409 and "shift" in e.value.detail.lower()

    _open(db, cashier)
    pay(db, cashier, bill_id, payment_method="cash")
    assert view(db, cashier, bill_id)["state"] == "paid"


def test_payments_allowed_without_shift_by_default(db, cashier, fake):
    bill_id = fake.create()
    pay(db, cashier, bill_id, payment_method="cash")
    assert view(db, cashier, bill_id)["state"] == "paid"


# ---------------------------------------------------------- voids and the drawer

def test_cash_void_in_the_same_shift_nets_to_zero(db, cashier, manager, fake):
    shift_id = _open(db, cashier, "1000000")
    bill_id = fake.create()
    pay(db, cashier, bill_id, payment_method="cash")
    svc.void_line(db, FAKE, bill_id, view(db, cashier, bill_id)["payments"][0]["id"], manager, "mistake")

    s = _summary(db, cashier, shift_id)
    assert (s.cash_sales, s.cash_voids, s.expected_cash) == (D("310000"), D("310000"), D("1000000"))
    assert s.methods[0].net_total == 0


def test_cash_void_after_close_is_money_out_of_the_next_shift(db, cashier, manager, fake):
    first = _open(db, cashier, "1000000")
    bill_id = fake.create()
    pay(db, cashier, bill_id, payment_method="cash")
    line_id = view(db, cashier, bill_id)["payments"][0]["id"]
    shifts.close_shift(db, first, cashier, D("1310000"), None)
    db.commit()
    second = _open(db, cashier, "200000")

    svc.void_line(db, FAKE, bill_id, line_id, manager, "refund next day")

    assert _summary(db, cashier, first).expected_cash == D("1310000")            # closed shift unchanged
    s2 = _summary(db, cashier, second)
    assert (s2.cash_sales, s2.cash_voids, s2.expected_cash) == (0, D("310000"), D("-110000"))
