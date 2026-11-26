# app/tests/test_billing_review.py
# Follow-up to roadmap item F: a device asked for a package the server could not apply.
# The event is accepted and the REAL session is opened, but it is flagged for billing review:
# payment is blocked until someone assigns a valid package or confirms normal pricing (audited).
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.tests._billiard_fixtures import *  # noqa: F401,F403
from app.tests.test_package_sessions import (  # noqa: F401  (device is a fixture)
    T0, _http_user, _setup, _start_event, device, make_package, make_product, make_rule, play,
)
from app.billiard.models import DeviceEvent, PaymentState, PricingRuleType, TableSession, TableStatus
from app.billiard.models.session import (
    BILLING_REVIEW_REQUIRED, BILLING_REVIEW_RESOLVED, REVIEW_ASSIGN_PACKAGE, REVIEW_CONFIRM_NORMAL,
)
from app.billiard.routes.session_router import router as session_router
from app.billiard.schemas.session import BillingReviewRequest
from app.billiard.services import session_lifecycle
from app.billiard.utils.billing import as_utc
from app.billiard.services.event_service import event_service
from app.billiard.services.payment_adapter import billiard_session_payable
from app.billiard.services.session_service import session_service
from app.billiard.services.table_service import table_service
from app.database import Base, get_db
from app.user.utils.token import get_current_user


D = Decimal


def flagged_session(db, device, table, package_id=99999):
    """A session opened by a controller event that asked for an unusable package."""
    res = event_service.ingest(db, device, [_start_event(table, package_id)])
    assert res.accepted == ["e1"]
    return db.execute(select(TableSession)).scalar_one()


# ---------------------------------------------------------------- the device path

@pytest.mark.parametrize("make, reason", [
    (lambda db: 99999, "Package not found"),
    (lambda db: make_package(db, client_id="c2").id, "Package not found"),        # other club: same answer, no leak
    (lambda db: make_package(db, active=False).id, "Package is not available"),
    ("not-a-number", "Invalid package_id"),
    (True, "Invalid package_id"),
])
def test_unusable_package_accepts_event_opens_session_and_flags_review(db, device, make, reason):
    _, table = _setup(db)
    package_id = make(db) if callable(make) else make
    s = flagged_session(db, device, table, package_id)
    assert s.billing_review_state == BILLING_REVIEW_REQUIRED and s.billing_review_reason == reason
    assert s.package_snapshot is None and s.package_id is None          # nothing purchased was invented
    db.refresh(table)
    assert table.status == TableStatus.PLAYING                          # the physical game is a real session
    row = db.execute(select(DeviceEvent)).scalar_one()
    assert row.status.value == "processed"                              # recorded and accepted, not rejected
    assert row.payload["reconciled"]["billing_review_required"] == reason


def test_requested_package_id_is_preserved(db, device):
    _, table = _setup(db)
    s = flagged_session(db, device, table, 99999)
    assert s.requested_package_id == 99999


def test_valid_package_from_device_is_not_flagged(db, device):
    _, table = _setup(db)
    pkg = make_package(db)
    s = flagged_session(db, device, table, pkg.id)
    assert s.billing_review_state is None and s.package_snapshot["package_id"] == pkg.id


def test_device_session_without_package_is_never_flagged(db, device):
    _, table = _setup(db)
    res = event_service.ingest(db, device, [_start_event(table)])
    s = db.execute(select(TableSession)).scalar_one()
    assert res.accepted == ["e1"] and s.billing_review_state is None and s.requested_package_id is None


def test_flagged_session_can_still_be_stopped_and_frees_the_table(db, device):
    user, table = _setup(db)
    s = flagged_session(db, device, table)
    session_service.stop_session(db, s.id, user)
    db.commit()
    db.refresh(table)
    assert table.status == TableStatus.AVAILABLE and s.status.value == "completed"
    assert s.billing_review_state == BILLING_REVIEW_REQUIRED            # stopping does not clear the review


def test_billed_as_played_while_review_is_pending(db, device):
    user, table = _setup(db)
    s = flagged_session(db, device, table)
    s.start_time = T0
    session_lifecycle.finalize_stop(db, s, table, None, at=T0 + timedelta(minutes=90))
    assert s.total_table_fee == D("150000.00")                          # normal rule, no package


# ---------------------------------------------------------------- notify + block payment

def test_board_and_bill_show_the_review(db, device):
    user, table = _setup(db)
    s = flagged_session(db, device, table, 77)
    row = next(r for r in table_service.get_active_tables(db, user) if r["session_id"] == s.id)
    assert row["needs_billing_review"] and row["requested_package_id"] == 77
    assert row["billing_review_reason"] == "Package not found"
    bill = session_service.build_bill(s)
    assert bill["needs_billing_review"] and bill["requested_package_id"] == 77 and bill["billing_review_resolution"] is None


def test_review_list_is_tenant_scoped_and_hides_resolved_and_cancelled(db, device):
    user, table = _setup(db)
    other = make_user(db, client_id="c2", name="u2")
    s = flagged_session(db, device, table)
    assert [r.session_id for r in session_service.list_billing_reviews(db, user)] == [s.id]
    assert session_service.list_billing_reviews(db, other) == []
    session_service.resolve_billing_review(db, s.id, "confirm_normal_pricing", None, "Customer paid for hours only", user)
    assert session_service.list_billing_reviews(db, user) == []


def test_payment_is_blocked_while_review_is_required(db, device):
    user, table = _setup(db)
    s = flagged_session(db, device, table)
    session_service.stop_session(db, s.id, user)
    with pytest.raises(HTTPException) as e:
        billiard_session_payable.check_payable(s)
    assert e.value.status_code == 409 and "Billing review required" in e.value.detail
    assert f"/sessions/{s.id}/billing-review" in e.value.detail and "Package not found" in e.value.detail


def test_payment_is_allowed_after_review_is_resolved(db, device):
    user, table = _setup(db)
    s = flagged_session(db, device, table)
    session_service.stop_session(db, s.id, user)
    session_service.resolve_billing_review(db, s.id, "confirm_normal_pricing", None, "Cashier checked with customer", user)
    billiard_session_payable.check_payable(s)           # no exception


def test_non_package_and_historical_sessions_stay_payable(db):
    _, table = _setup(db)
    s = play(db, table, 30)
    assert s.billing_review_state is None
    billiard_session_payable.check_payable(s)
    assert session_service.build_bill(s)["needs_billing_review"] is False


# ---------------------------------------------------------------- resolving

def test_confirm_normal_pricing_records_the_decision(db, device):
    user, table = _setup(db)
    s = flagged_session(db, device, table, 5)
    session_service.stop_session(db, s.id, user)
    before = (s.total_table_fee, s.grand_total, dict(s.pricing_snapshot))
    session_service.resolve_billing_review(db, s.id, "confirm_normal_pricing", None, "Walk-in, no package", user)
    assert s.billing_review_state == BILLING_REVIEW_RESOLVED and s.billing_review_resolution == REVIEW_CONFIRM_NORMAL
    assert s.billing_review_note == "Walk-in, no package"
    assert s.billing_reviewed_by_id == user.id and s.billing_reviewed_at is not None
    assert s.requested_package_id == 5 and s.billing_review_reason == "Package not found"     # history kept
    assert (s.total_table_fee, s.grand_total, dict(s.pricing_snapshot)) == before            # money unchanged
    assert s.package_snapshot is None


def test_assign_package_after_stop_recomputes_the_bill(db, device):
    user, table = _setup(db)
    s = flagged_session(db, device, table)
    s.start_time = T0
    session_lifecycle.finalize_stop(db, s, table, None, at=T0 + timedelta(minutes=90))
    assert s.grand_total == D("150000.00")
    pkg = make_package(db)                                               # 60 min for 80,000
    db.commit()
    session_service.resolve_billing_review(db, s.id, "assign_package", pkg.id, None, user)
    assert s.package_snapshot["package_id"] == pkg.id and s.package_name == "1h Combo"
    assert s.total_table_fee == D("130000.00") and s.grand_total == D("130000.00")   # 80,000 + 30 min at the rate
    assert s.billing_review_resolution == REVIEW_ASSIGN_PACKAGE and s.billing_reviewed_by_id == user.id
    assert s.requested_package_id == 99999                               # what the device asked is not overwritten
    assert session_service.build_bill(s)["overtime_minutes"] == 30


def test_assign_package_keeps_discount_after_stop(db, device):
    user, table = _setup(db)
    s = flagged_session(db, device, table)
    s.start_time = T0
    session_lifecycle.apply_discount(s, percent=D("10"), by_id=user.id)
    session_lifecycle.finalize_stop(db, s, table, None, at=T0 + timedelta(minutes=60))
    pkg = make_package(db, price="50000")
    db.commit()
    session_service.resolve_billing_review(db, s.id, "assign_package", pkg.id, None, user)
    assert s.total_table_fee == D("50000.00") and s.discount == D("5000.00") and s.grand_total == D("45000.00")


def test_assign_package_on_an_active_session_sets_ends_at_and_free_items(db, device):
    user, table = _setup(db)
    beer = make_product(db)
    s = flagged_session(db, device, table)
    session_service.add_item(db, s.id, beer.id, 3, None, user)           # charged in full: no package yet
    assert s.total_product_fee == D("60000.00")
    pkg = make_package(db, items=[(beer.id, 2)])
    db.commit()
    session_service.resolve_billing_review(db, s.id, "assign_package", pkg.id, None, user)
    assert s.ends_at is not None
    assert sorted((i.quantity, i.from_package, i.total_price) for i in s.items) == [
        (1, False, D("20000.00")), (2, True, D("0.00"))]                 # 2 of the 3 beers are now free
    assert s.total_product_fee == D("20000.00")
    assert sum(i.quantity for i in s.items) == 3


def test_assign_package_converts_a_whole_line_when_it_fits(db, device):
    user, table = _setup(db)
    beer = make_product(db)
    s = flagged_session(db, device, table)
    session_service.add_item(db, s.id, beer.id, 2, None, user)
    pkg = make_package(db, items=[(beer.id, 5)])
    db.commit()
    session_service.resolve_billing_review(db, s.id, "assign_package", pkg.id, None, user)
    (item,) = s.items
    assert item.from_package and item.quantity == 2 and item.unit_price == 0 and item.product_name == "Beer (package)"
    # later additions use what is left of the allowance (3 more)
    again = session_service.add_item(db, s.id, beer.id, 4, None, user)
    assert not again.from_package and again.quantity == 1


def test_assign_package_does_not_move_an_existing_ends_at(db, device):
    user, table = _setup(db)
    s = flagged_session(db, device, table)
    session_lifecycle.extend_session(s, 30)
    ends = as_utc(s.ends_at)
    pkg = make_package(db, minutes=120)
    db.commit()
    session_service.resolve_billing_review(db, s.id, "assign_package", pkg.id, None, user)
    assert as_utc(s.ends_at) == ends               # the 30-minute extension was kept


@pytest.mark.parametrize("setup, status", [
    ("no_review", 409), ("twice", 409), ("inactive", 400), ("other_club", 404), ("unknown", 404),
])
def test_assign_package_errors(db, device, setup, status):
    user, table = _setup(db)
    s = flagged_session(db, device, table)
    pkg_id = {                                   # lazily: one package per case (names are unique per club)
        "no_review": lambda: make_package(db).id, "twice": lambda: make_package(db).id,
        "inactive": lambda: make_package(db, active=False).id,
        "other_club": lambda: make_package(db, client_id="c2").id, "unknown": lambda: 424242,
    }[setup]()
    if setup == "no_review":
        s.billing_review_state = None
    if setup == "twice":
        session_service.resolve_billing_review(db, s.id, "assign_package", pkg_id, None, user)
    db.commit()
    with pytest.raises(HTTPException) as e:
        session_service.resolve_billing_review(db, s.id, "assign_package", pkg_id, None, user)
    assert e.value.status_code == status


def test_resolve_on_a_cancelled_or_paying_session_is_409(db, device):
    user, table = _setup(db)
    s = flagged_session(db, device, table)
    s.payment_state = PaymentState.PENDING
    db.commit()
    with pytest.raises(HTTPException) as e:
        session_service.resolve_billing_review(db, s.id, "confirm_normal_pricing", None, "check", user)
    assert e.value.status_code == 409
    s.payment_state = PaymentState.UNPAID
    session_service.cancel_session(db, s.id, "opened by mistake", user)
    db.commit()
    with pytest.raises(HTTPException) as e:
        session_service.resolve_billing_review(db, s.id, "confirm_normal_pricing", None, "check", user)
    assert e.value.status_code == 409
    assert session_service.list_billing_reviews(db, user) == []          # cancelled sessions are not "waiting"


def test_other_club_cannot_resolve(db, device):
    _, table = _setup(db)
    s = flagged_session(db, device, table)
    stranger = make_user(db, client_id="c2", name="u2")
    with pytest.raises(HTTPException) as e:
        session_service.resolve_billing_review(db, s.id, "confirm_normal_pricing", None, "check", stranger)
    assert e.value.status_code == 404


def test_request_validation():
    with pytest.raises(ValidationError):
        BillingReviewRequest(action="assign_package")                    # needs package_id
    with pytest.raises(ValidationError):
        BillingReviewRequest(action="confirm_normal_pricing")            # needs a note
    with pytest.raises(ValidationError):
        BillingReviewRequest(action="confirm_normal_pricing", note="  ")
    with pytest.raises(ValidationError):
        BillingReviewRequest(action="confirm_normal_pricing", note="ok ok", package_id=3)
    with pytest.raises(ValidationError):
        BillingReviewRequest(action="whatever", note="abc")
    assert BillingReviewRequest(action="assign_package", package_id=3).note is None


def test_device_events_never_overwrite_package_terms_or_billing(db, device):
    """A second session_start (replay / adopt) must not change a purchased package or the flag."""
    user, table = _setup(db)
    pkg = make_package(db)
    s = table_service.start_session(db, table.id, user, package_id=pkg.id)
    db.commit()
    snap = dict(s.package_snapshot)
    res = event_service.ingest(db, device, [_start_event(table, 424242)])      # device asks for another package
    assert res.accepted == ["e1"]
    db.refresh(s)
    assert s.package_snapshot == snap and s.billing_review_state is None and s.requested_package_id is None


# ---------------------------------------------------------------- HTTP

@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    seed = Session()
    user = make_user(seed)
    table = make_table(seed)
    beer = make_product(seed)
    pkg = make_package(seed, items=[(beer.id, 1)])
    seed.commit()
    s = session_lifecycle.open_session(seed, table, None, at=T0)
    session_lifecycle.flag_billing_review(s, 31337, "Package not found")
    seed.commit()
    ids = SimpleNamespace(user_id=user.id, session_id=s.id, package_id=pkg.id, beer_id=beer.id)
    seed.close()

    app = FastAPI()
    app.include_router(session_router)

    def _db():
        sess = Session()
        try:
            yield sess
        finally:
            sess.close()

    holder = {"u": _http_user()}
    holder["u"].id = ids.user_id
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: holder["u"]
    c = TestClient(app)
    c.ids, c.holder = ids, holder
    return c


def test_http_list_then_resolve_with_package(client):
    rows = client.get("/sessions/billing-review").json()                # not swallowed by /{session_id}
    assert [r["session_id"] for r in rows] == [client.ids.session_id]
    assert rows[0]["requested_package_id"] == 31337 and rows[0]["reason"] == "Package not found"

    client.post(f"/sessions/{client.ids.session_id}/stop")
    pay_blocked = client.get(f"/sessions/{client.ids.session_id}").json()
    assert pay_blocked["needs_billing_review"] is True

    r = client.post(f"/sessions/{client.ids.session_id}/billing-review",
                    json={"action": "assign_package", "package_id": client.ids.package_id})
    assert r.status_code == 200
    bill = r.json()
    assert bill["needs_billing_review"] is False and bill["package_name"] == "1h Combo"
    assert bill["billing_review_resolution"] == "assign_package" and bill["billing_reviewed_by"] == "u1"
    assert bill["billing_reviewed_at"] is not None and bill["requested_package_id"] == 31337
    assert client.get("/sessions/billing-review").json() == []


def test_http_confirm_needs_note_and_second_call_is_409(client):
    url = f"/sessions/{client.ids.session_id}/billing-review"
    assert client.post(url, json={"action": "confirm_normal_pricing"}).status_code == 422
    assert client.post(url, json={"action": "confirm_normal_pricing", "note": "ok per customer"}).status_code == 200
    assert client.post(url, json={"action": "confirm_normal_pricing", "note": "again"}).status_code == 409


def test_http_other_club_gets_404_and_empty_list(client):
    client.holder["u"] = _http_user("other-club")
    assert client.get("/sessions/billing-review").json() == []
    url = f"/sessions/{client.ids.session_id}/billing-review"
    assert client.post(url, json={"action": "confirm_normal_pricing", "note": "abc"}).status_code == 404


# ---------------------------------------------------------------- items: all created lines

def test_http_items_returns_every_created_line(client):
    sid, beer = client.ids.session_id, client.ids.beer_id
    client.post(f"/sessions/{sid}/billing-review",
                json={"action": "assign_package", "package_id": client.ids.package_id})   # 1 beer included
    r = client.post(f"/sessions/{sid}/items", json={"product_id": beer, "quantity": 3})
    body = r.json()
    assert r.status_code == 201
    assert [(l["quantity"], l["from_package"]) for l in body["lines"]] == [(1, True), (2, False)]   # free first
    assert (body["quantity"], body["from_package"], body["total_price"]) == (2, False, "40000.00")    # top level: paid line
    assert body["id"] == body["lines"][-1]["id"]


def test_http_items_with_a_single_line_has_one_entry(client):
    sid, beer = client.ids.session_id, client.ids.beer_id
    body = client.post(f"/sessions/{sid}/items", json={"product_id": beer, "quantity": 2}).json()
    assert len(body["lines"]) == 1 and body["lines"][0]["id"] == body["id"]
    assert body["from_package"] is False and body["total_price"] == "40000.00"
