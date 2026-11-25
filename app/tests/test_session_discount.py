# app/tests/test_session_discount.py
# Roadmap item C: manager-only discount (fixed or percent) on table fee + products.
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.tests._billiard_fixtures import *  # noqa: F401,F403
from app.billiard.models import PaymentState, SessionStatus
from app.billiard.routes.session_router import router
from app.billiard.schemas.session import DiscountRequest
from app.billiard.services import session_lifecycle
from app.billiard.services.payment_adapter import billiard_session_payable
from app.billiard.services.report_service import report_service
from app.billiard.services.session_service import session_service
from app.billiard.services.table_service import table_service
from app.database import Base, get_db
from app.product.models.product import Product
from app.user.utils.token import get_current_user

D = Decimal


def _active(db, client_id="c1"):
    user = make_user(db, client_id=client_id)
    table = make_table(db, client_id=client_id)
    s = table_service.start_session(db, table.id, user)
    db.commit()
    return user, table, s


def _add_beer(db, user, s, qty=2, price="25000"):
    p = Product(name="Beer", base_price=D(price))
    db.add(p)
    db.flush()
    session_service.add_item(db, s.id, p.id, qty, None, user)


def _completed(db, fee="260000", beer_qty=2):
    """Completed, unpaid session with a known table fee (260,000) and 2 x 25,000 of products."""
    user, table, s = _active(db)
    _add_beer(db, user, s, beer_qty)
    session_service.stop_session(db, s.id, user)
    s.total_table_fee = D(fee)
    session_lifecycle.recompute_totals(s)
    db.commit()
    return user, s


def _discount(db, user, s, amount=None, percent=None, reason="regular customer"):
    return session_service.set_discount(
        db, s.id, None if amount is None else D(str(amount)), None if percent is None else D(str(percent)),
        reason, user,
    )


# ---------------------------------------------------------------- amounts

def test_no_discount_changes_nothing(db):
    _, s = _completed(db)
    assert s.discount == D("0")
    assert s.grand_total == D("310000")


def test_fixed_discount_reduces_grand_total(db):
    user, s = _completed(db)
    _discount(db, user, s, amount=5000)
    assert s.discount == D("5000") and s.grand_total == D("305000")
    assert s.total_table_fee == D("260000") and s.total_product_fee == D("50000")   # parts untouched


def test_percent_discount_is_converted_to_amount(db):
    user, s = _completed(db)
    _discount(db, user, s, percent=10)
    assert s.discount == D("31000.00") and s.grand_total == D("279000.00")


def test_discount_cannot_exceed_total(db):
    user, s = _completed(db)
    _discount(db, user, s, amount=999999)
    assert s.discount == D("310000") and s.grand_total == D("0")      # clamped, never negative


def test_hundred_percent_makes_it_free(db):
    user, s = _completed(db)
    _discount(db, user, s, percent=100)
    assert s.grand_total == D("0")


def test_remove_discount_restores_total(db):
    user, s = _completed(db)
    _discount(db, user, s, percent=10)
    _discount(db, user, s, amount=0, reason=None)
    assert s.discount == D("0") and s.grand_total == D("310000")
    assert s.discount_reason is None and session_lifecycle.discount_spec(s) is None


def test_changing_discount_replaces_the_old_one(db):
    user, s = _completed(db)
    _discount(db, user, s, percent=10)
    _discount(db, user, s, amount=1000, reason="manager decision")
    assert s.discount == D("1000") and s.grand_total == D("309000")
    assert s.discount_reason == "manager decision"


def test_discount_records_who_and_why(db):
    user, s = _completed(db)
    _discount(db, user, s, amount=5000, reason="birthday")
    bill = session_service.build_bill(s)
    assert bill["discount"] == D("5000") and bill["discount_reason"] == "birthday"
    assert bill["discounted_by"] == user.username and bill["discount_percent"] is None
    assert bill["grand_total"] == D("305000")


def test_bill_shows_percent_when_given_as_percent(db):
    user, s = _completed(db)
    _discount(db, user, s, percent=15)
    assert session_service.build_bill(s)["discount_percent"] == D("15")


# ---------------------------------------------------------------- during play / at Stop

def test_discount_set_during_play_survives_stop(db):
    user, _, s = _active(db)
    _add_beer(db, user, s, 2)                         # 50,000 of products
    _discount(db, user, s, amount=5000)
    stopped = session_service.stop_session(db, s.id, user)
    assert stopped.discount == D("5000")
    assert stopped.grand_total == stopped.total_table_fee + D("50000") - D("5000")


def test_percent_discount_is_recomputed_at_stop_with_the_final_fee(db):
    user, _, s = _active(db)
    _add_beer(db, user, s, 2)
    _discount(db, user, s, percent=10)
    assert s.discount == D("5000.00")                 # table fee is still 0 while playing
    s.start_time = datetime.now(timezone.utc) - timedelta(hours=2)
    stopped = session_service.stop_session(db, s.id, user)
    assert stopped.total_table_fee > 0
    expected = ((stopped.total_table_fee + D("50000")) * D("10") / D("100")).quantize(D("0.01"))
    assert stopped.discount == expected and stopped.discount != D("5000.00")


def test_percent_follows_items_added_later(db):
    user, _, s = _active(db)
    _add_beer(db, user, s, 2)
    _discount(db, user, s, percent=10)
    _add_beer(db, user, s, 2)
    assert s.total_product_fee == D("100000") and s.discount == D("10000.00")
    assert s.grand_total == D("90000.00")


def test_fixed_discount_set_before_any_charge_applies_once_there_is_something_to_discount(db):
    user, _, s = _active(db)
    _discount(db, user, s, amount=5000)
    assert s.discount == D("0")                        # nothing to discount yet
    _add_beer(db, user, s, 2)
    assert s.discount == D("5000") and s.grand_total == D("45000")


def test_live_total_in_active_tables_subtracts_the_discount(db):
    user, table, s = _active(db)
    _add_beer(db, user, s, 2)
    _discount(db, user, s, amount=5000)
    db.commit()
    row = next(r for r in table_service.get_active_tables(db, user) if r["session_id"] == s.id)
    assert row["current_discount"] == D("5000")
    assert row["current_total"] == row["current_table_fee"] + row["current_product_fee"] - D("5000")


def test_live_total_equals_stop_total_with_discount(db):
    user, _, s = _active(db)
    _add_beer(db, user, s, 2)
    _discount(db, user, s, percent=10)
    # 30 min 10 s in: the two calls below run within the same billable minute
    s.start_time = datetime.now(timezone.utc) - timedelta(minutes=30, seconds=10)
    db.commit()
    live = next(r for r in table_service.get_active_tables(db, user) if r["session_id"] == s.id)
    stopped = session_service.stop_session(db, s.id, user)
    assert stopped.discount == live["current_discount"]
    assert stopped.grand_total == live["current_total"]


# ---------------------------------------------------------------- rules

def test_discount_after_payment_order_created_is_409(db):
    user, s = _completed(db)
    s.payment_order_id = 1                              # a payment order now fixes the total
    db.commit()
    with pytest.raises(HTTPException) as e:
        _discount(db, user, s, amount=5000)
    assert e.value.status_code == 409 and "payment" in e.value.detail


def test_discount_on_paid_legacy_session_is_409(db):
    user, s = _completed(db)
    s.payment_state = PaymentState.PAID                 # settled before the Payments module kept orders
    db.commit()
    with pytest.raises(HTTPException) as e:
        _discount(db, user, s, amount=5000)
    assert e.value.status_code == 409


def test_discount_on_cancelled_session_is_409(db):
    user, _, s = _active(db)
    session_service.cancel_session(db, s.id, "opened by mistake", user)
    db.commit()
    with pytest.raises(HTTPException) as e:
        _discount(db, user, s, amount=5000)
    assert e.value.status_code == 409


def test_other_tenant_404(db):
    _, s = _completed(db)
    other = make_user(db, client_id="c2", name="u2")
    with pytest.raises(HTTPException) as e:
        _discount(db, other, s, amount=5000)
    assert e.value.status_code == 404 and s.discount == D("0")


def test_percent_over_100_is_422_in_the_service_too(db):
    user, s = _completed(db)
    with pytest.raises(HTTPException) as e:
        _discount(db, user, s, percent=150)
    assert e.value.status_code == 422


def test_both_amount_and_percent_is_rejected():
    with pytest.raises(ValidationError):
        DiscountRequest(amount=1000, percent=10, reason="both")


def test_neither_amount_nor_percent_is_rejected():
    with pytest.raises(ValidationError):
        DiscountRequest(reason="nothing")


def test_negative_amount_and_zero_or_over_100_percent_are_rejected():
    for bad in ({"amount": -1}, {"percent": 0}, {"percent": 101}, {"percent": -5}):
        with pytest.raises(ValidationError):
            DiscountRequest(reason="bad value", **bad)


def test_reason_is_required_when_applying_but_not_when_removing():
    with pytest.raises(ValidationError):
        DiscountRequest(amount=1000)
    with pytest.raises(ValidationError):
        DiscountRequest(percent=10, reason=" ab ")
    assert DiscountRequest(amount=0).amount == 0       # removing needs no reason


# ---------------------------------------------------------------- money flows

def test_payment_quote_uses_the_discounted_grand_total(db):
    user, s = _completed(db)
    _discount(db, user, s, percent=10)
    db.commit()
    assert billiard_session_payable.quote(s).total == s.grand_total == D("279000.00")


def test_usage_report_shows_discount_total_and_the_arithmetic_holds(db):
    user, s = _completed(db)
    _discount(db, user, s, amount=5000)
    s.payment_state = PaymentState.PAID
    db.commit()
    totals = report_service.table_usage(db, user).totals
    assert totals.discount_total == D("5000")
    assert totals.table_revenue + totals.product_revenue - totals.discount_total == totals.total_revenue
    assert totals.total_revenue == D("305000")


def test_report_ignores_discount_of_unpaid_sessions(db):
    user, s = _completed(db)
    _discount(db, user, s, amount=5000)
    totals = report_service.table_usage(db, user).totals
    assert totals.discount_total == D("0") and totals.unpaid_total == D("305000")


# ---------------------------------------------------------------- HTTP

def _http_user(role="manager", client_id="c1"):
    return SimpleNamespace(
        id=1, client_id=client_id, username="boss",
        is_super_admin=lambda: False, has_role=lambda r: r == role,
    )


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    seed = Session()
    user = make_user(seed)
    table = make_table(seed)
    s = table_service.start_session(seed, table.id, user)
    _add_beer(seed, user, s, 2)
    seed.commit()
    sid = s.id
    seed.close()

    app = FastAPI()
    app.include_router(router)

    def _db():
        sess = Session()
        try:
            yield sess
        finally:
            sess.close()

    holder = {"u": _http_user()}
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: holder["u"]
    c = TestClient(app)
    c.sid, c.holder = sid, holder
    return c


def test_http_fixed_discount_returns_the_updated_bill(client):
    r = client.post(f"/sessions/{client.sid}/discount", json={"amount": 5000, "reason": "regular"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert D(str(body["discount"])) == 5000 and D(str(body["grand_total"])) == 45000
    assert body["discount_reason"] == "regular"


def test_http_percent_discount(client):
    r = client.post(f"/sessions/{client.sid}/discount", json={"percent": 10, "reason": "promo"})
    assert r.status_code == 200 and D(str(r.json()["discount_percent"])) == 10


def test_http_remove_discount_with_zero(client):
    client.post(f"/sessions/{client.sid}/discount", json={"amount": 5000, "reason": "regular"})
    r = client.post(f"/sessions/{client.sid}/discount", json={"amount": 0})
    assert r.status_code == 200 and D(str(r.json()["discount"])) == 0


def test_http_validation_errors_are_422(client):
    url = f"/sessions/{client.sid}/discount"
    assert client.post(url, json={}).status_code == 422
    assert client.post(url, json={"amount": 1000, "percent": 10, "reason": "both"}).status_code == 422
    assert client.post(url, json={"amount": -5, "reason": "negative"}).status_code == 422
    assert client.post(url, json={"percent": 150, "reason": "too much"}).status_code == 422
    assert client.post(url, json={"amount": 1000}).status_code == 422          # no reason


def test_http_discount_is_manager_only(client):
    client.holder["u"] = _http_user("staff")
    r = client.post(f"/sessions/{client.sid}/discount", json={"amount": 5000, "reason": "regular"})
    assert r.status_code == 403


def test_http_other_tenant_404(client):
    client.holder["u"] = _http_user(client_id="other-club")
    r = client.post(f"/sessions/{client.sid}/discount", json={"amount": 5000, "reason": "regular"})
    assert r.status_code == 404


def test_http_discount_survives_stop_and_shows_on_the_receipt(client):
    client.post(f"/sessions/{client.sid}/discount", json={"amount": 5000, "reason": "regular"})
    stop = client.post(f"/sessions/{client.sid}/stop")
    assert stop.status_code == 200, stop.text
    assert D(str(stop.json()["discount"])) == 5000
    bill = client.get(f"/sessions/{client.sid}").json()
    assert D(str(bill["grand_total"])) == D(str(bill["total_table_fee"])) + D("50000") - D("5000")
