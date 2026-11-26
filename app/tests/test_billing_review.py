# app/tests/test_billing_review.py
# Follow-up to roadmap item F: a device asked for a package the server could not apply.
# The event is accepted and the REAL session is opened, but it is flagged for billing review:
# payment is blocked until someone assigns a valid package or confirms normal pricing (audited).
import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.tests._billiard_fixtures import *  # noqa: F401,F403
from app.tests.test_package_sessions import (  # noqa: F401  (device is a fixture)
    T0, _setup, _start_event, device, make_package, make_product, make_rule, play,
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
from app.billiard.utils.permissions import (
    BILLING_REVIEW_RESOLVE, BILLING_REVIEW_VIEW, has_billiard_permission,
)
from app.database import Base, get_db
from app.user.models.role import Role
from app.user.models.user import User
from app.user.models.user_role import UserRole
from app.user.utils.token import get_current_user


D = Decimal


def fresh(db, s):
    """Reload the session from the database (drops anything cached in the identity map)."""
    db.expire_all()
    return db.get(TableSession, s.id)


def grant(db, user, role_name, permissions=()):
    """Give `user` a role (created once, with these permissions) through the existing Role / UserRole tables."""
    role = db.execute(select(Role).where(Role.name == role_name)).scalar_one_or_none()
    if role is None:
        role = Role(name=role_name, display_name=role_name, permissions=json.dumps(list(permissions)))
        db.add(role)
        db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.flush()
    db.expire(user, ["user_roles"])
    return user


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


# ---------------------------------------------------------------- permissions

def test_default_grants_and_implied_view(db):
    admin = grant(db, make_user(db, name="a"), "admin", ["*"])
    manager = grant(db, make_user(db, name="m"), "manager")                    # no permission entry at all
    plain = grant(db, make_user(db, name="p"), "cashier")
    viewer = grant(db, make_user(db, name="v"), "review_viewer", [BILLING_REVIEW_VIEW])
    resolver = grant(db, make_user(db, name="r"), "trusted_cashier", [BILLING_REVIEW_RESOLVE])
    for user in (admin, manager):
        assert has_billiard_permission(user, BILLING_REVIEW_VIEW) and has_billiard_permission(user, BILLING_REVIEW_RESOLVE)
    assert not has_billiard_permission(plain, BILLING_REVIEW_VIEW) and not has_billiard_permission(plain, BILLING_REVIEW_RESOLVE)
    assert has_billiard_permission(viewer, BILLING_REVIEW_VIEW) and not has_billiard_permission(viewer, BILLING_REVIEW_RESOLVE)
    assert has_billiard_permission(resolver, BILLING_REVIEW_RESOLVE) and has_billiard_permission(resolver, BILLING_REVIEW_VIEW)


# (club, role, role permissions) for the HTTP users. The manager role has NO permission entry: it is a default grant.
HTTP_USERS = {
    "manager": ("c1", "manager", []),
    "admin": ("c1", "admin", ["*"]),
    "cashier": ("c1", "cashier", []),
    "trusted": ("c1", "trusted_cashier", [BILLING_REVIEW_RESOLVE]),
    "viewer": ("c1", "review_viewer", [BILLING_REVIEW_VIEW]),
    "other": ("c2", "manager", []),
}


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine)
    seed = Session_()
    users = {}
    for key, (club, role, perms) in HTTP_USERS.items():
        name = "u1" if key == "manager" else key
        users[key] = grant(seed, make_user(seed, client_id=club, name=name), role, perms).id
    table = make_table(seed)
    beer = make_product(seed)
    pkg = make_package(seed, items=[(beer.id, 1)])
    seed.commit()
    s = session_lifecycle.open_session(seed, table, None, at=T0)
    session_lifecycle.flag_billing_review(s, 31337, "Package not found")
    seed.commit()
    ids = SimpleNamespace(users=users, session_id=s.id, package_id=pkg.id, beer_id=beer.id)
    seed.close()

    app = FastAPI()
    app.include_router(session_router)
    holder = {"id": users["manager"]}

    def _db():
        sess = Session_()
        try:
            yield sess
        finally:
            sess.close()                       # nothing committed => everything of the request is rolled back

    def _current_user(db: Session = Depends(get_db)):
        return db.get(User, holder["id"])      # a real User: real roles, real permissions

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _current_user
    c = TestClient(app, raise_server_exceptions=False)
    c.ids, c.engine, c.sessionmaker = ids, engine, Session_
    c.act_as = lambda key: holder.__setitem__("id", users[key])
    return c


def review_state(client):
    """The flagged session as stored (a fresh connection, so uncommitted work is invisible)."""
    s = client.sessionmaker()
    try:
        row = s.get(TableSession, client.ids.session_id)
        return {
            "state": row.billing_review_state, "package": row.package_snapshot, "audit": row.billing_review_audit,
            "resolution": row.billing_review_resolution, "by": row.billing_reviewed_by_id,
            "items": sorted((i.quantity, i.from_package, str(i.total_price)) for i in row.items),
            "money": (str(row.total_table_fee), str(row.total_product_fee), str(row.discount), str(row.grand_total)),
            "requested": row.requested_package_id, "reason": row.billing_review_reason,
        }
    finally:
        s.close()


def test_cashier_without_the_permission_gets_403(client):
    client.act_as("cashier")
    before = review_state(client)
    listing = client.get("/sessions/billing-review")
    assert listing.status_code == 403 and BILLING_REVIEW_VIEW in listing.json()["detail"]
    for body in ({"action": "confirm_normal_pricing", "note": "I say it is fine"},
                 {"action": "assign_package", "package_id": client.ids.package_id}):
        r = client.post(f"/sessions/{client.ids.session_id}/billing-review", json=body)
        assert r.status_code == 403 and BILLING_REVIEW_RESOLVE in r.json()["detail"]
    assert review_state(client) == before                                    # nothing changed
    assert review_state(client)["state"] == "required"


def test_cashier_still_sees_the_indicator_on_the_bill(client):
    client.act_as("cashier")
    bill = client.get(f"/sessions/{client.ids.session_id}").json()
    assert bill["needs_billing_review"] is True and bill["billing_review_reason"] == "Package not found"


def test_view_permission_lists_but_cannot_resolve(client):
    client.act_as("viewer")
    rows = client.get("/sessions/billing-review").json()
    assert [r["session_id"] for r in rows] == [client.ids.session_id]
    r = client.post(f"/sessions/{client.ids.session_id}/billing-review",
                    json={"action": "confirm_normal_pricing", "note": "viewer tries"})
    assert r.status_code == 403
    assert review_state(client)["state"] == "required"


def test_trusted_cashier_with_resolve_permission_can_list_and_resolve(client):
    client.act_as("trusted")
    assert len(client.get("/sessions/billing-review").json()) == 1          # resolve implies view
    r = client.post(f"/sessions/{client.ids.session_id}/billing-review",
                    json={"action": "assign_package", "package_id": client.ids.package_id})
    assert r.status_code == 200 and r.json()["billing_reviewed_by"] == "trusted"
    assert r.json()["billing_review_audit"]["resolver_roles"] == ["trusted_cashier"]


@pytest.mark.parametrize("who", ["manager", "admin"])
def test_manager_and_admin_resolve_by_default(client, who):
    client.act_as(who)
    assert len(client.get("/sessions/billing-review").json()) == 1
    r = client.post(f"/sessions/{client.ids.session_id}/billing-review",
                    json={"action": "confirm_normal_pricing", "note": "Checked at the desk"})
    assert r.status_code == 200 and r.json()["needs_billing_review"] is False


def test_http_list_then_resolve_with_package(client):
    rows = client.get("/sessions/billing-review").json()                # not swallowed by /{session_id}
    assert [r["session_id"] for r in rows] == [client.ids.session_id]
    assert rows[0]["requested_package_id"] == 31337 and rows[0]["reason"] == "Package not found"

    client.post(f"/sessions/{client.ids.session_id}/stop")
    assert client.get(f"/sessions/{client.ids.session_id}").json()["needs_billing_review"] is True

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
    client.act_as("other")                                                  # a manager, but of ANOTHER club
    assert client.get("/sessions/billing-review").json() == []
    url = f"/sessions/{client.ids.session_id}/billing-review"
    assert client.post(url, json={"action": "confirm_normal_pricing", "note": "abc"}).status_code == 404


def test_failed_resolution_over_http_changes_nothing(client, monkeypatch):
    sid = client.ids.session_id
    client.post(f"/sessions/{sid}/items", json={"product_id": client.ids.beer_id, "quantity": 2})
    before = review_state(client)

    def boom(session):
        raise RuntimeError("disk full")
    monkeypatch.setattr(session_lifecycle, "recompute_totals", boom)       # fails AFTER the package was applied
    r = client.post(f"/sessions/{sid}/billing-review", json={"action": "assign_package", "package_id": client.ids.package_id})
    assert r.status_code == 500
    assert review_state(client) == before and review_state(client)["package"] is None
    monkeypatch.undo()
    ok = client.post(f"/sessions/{sid}/billing-review", json={"action": "assign_package", "package_id": client.ids.package_id})
    assert ok.status_code == 200                                            # and it is still resolvable


# ---------------------------------------------------------------- audit and transaction (service level)

def _manager(db, name="m"):
    return grant(db, make_user(db, name=name), "manager")


def test_confirm_keeps_a_complete_audit_record(db, device):
    user, table = _setup(db)
    manager = _manager(db)
    s = flagged_session(db, device, table, 5)
    session_service.stop_session(db, s.id, user)
    db.commit()
    money = (s.total_table_fee, s.total_product_fee, s.discount, s.grand_total)
    session_service.resolve_billing_review(db, s.id, "confirm_normal_pricing", None, "Walk-in, no package", manager)
    db.commit()
    s = fresh(db, s)
    audit = s.billing_review_audit
    assert audit["action"] == "confirm_normal_pricing" and audit["resolver_roles"] == ["manager"]
    assert audit["requested_package_id"] == 5 and audit["reason"] == "Package not found"
    assert audit["before"] == audit["after"] and audit["before"]["package"] is None
    assert audit["before"]["grand_total"] == str(money[3])
    # the columns agree with the audit and the original request survives
    assert (s.billing_review_note, s.billing_reviewed_by_id, s.billing_review_resolution) == (
        "Walk-in, no package", manager.id, "confirm_normal_pricing")
    assert s.billing_reviewed_at is not None and s.requested_package_id == 5 and s.billing_review_reason == "Package not found"
    json.dumps(audit)                                                        # plain JSON


def test_assign_keeps_a_complete_audit_record_with_before_and_after(db, device):
    user, table = _setup(db)
    manager = _manager(db)
    beer = make_product(db)
    s = flagged_session(db, device, table, 77)
    session_service.add_item(db, s.id, beer.id, 3, None, user)              # 60,000 of beer, no package yet
    s.start_time = T0
    session_lifecycle.apply_discount(s, percent=D("10"), by_id=user.id)
    session_lifecycle.finalize_stop(db, s, table, None, at=T0 + timedelta(minutes=90))
    pkg = make_package(db, items=[(beer.id, 2)])                            # 60 min for 80,000 + 2 free beers
    db.commit()
    assert s.grand_total == D("189000.00")                                   # (150,000 + 60,000) - 10%

    session_service.resolve_billing_review(db, s.id, "assign_package", pkg.id, "Customer showed the voucher", manager)
    db.commit()
    s = fresh(db, s)
    audit = s.billing_review_audit
    assert audit["action"] == "assign_package" and audit["resolver_roles"] == ["manager"]
    assert audit["requested_package_id"] == 77 and audit["reason"] == "Package not found"
    assert audit["before"] == {
        "total_table_fee": "150000.00", "total_product_fee": "60000.00", "discount": "21000.00",
        "grand_total": "189000.00", "free_units": 0, "package": None}
    assert audit["after"]["package"] == {"package_id": pkg.id, "name": "1h Combo", "price": "80000.00", "duration_minutes": 60}
    assert audit["after"]["free_units"] == 2
    assert audit["after"]["total_table_fee"] == "130000.00" and audit["after"]["total_product_fee"] == "20000.00"
    assert audit["after"]["discount"] == "15000.00" and audit["after"]["grand_total"] == "135000.00"   # 10% still applies
    assert s.grand_total == D("135000.00")
    assert s.requested_package_id == 77                                      # the device's request is never overwritten


def test_audit_is_written_once_and_a_second_resolution_cannot_change_it(db, device):
    user, table = _setup(db)
    manager = _manager(db)
    s = flagged_session(db, device, table)
    session_service.resolve_billing_review(db, s.id, "confirm_normal_pricing", None, "first decision", manager)
    db.commit()
    first = json.loads(json.dumps(fresh(db, s).billing_review_audit))
    pkg = make_package(db)
    db.commit()
    with pytest.raises(HTTPException) as e:
        session_service.resolve_billing_review(db, s.id, "assign_package", pkg.id, "second", manager)
    assert e.value.status_code == 409
    again = fresh(db, s)
    assert again.billing_review_audit == first and again.billing_review_note == "first decision"
    assert again.package_snapshot is None


def test_bill_exposes_the_audit(db, device):
    user, table = _setup(db)
    s = flagged_session(db, device, table)
    assert session_service.build_bill(s)["billing_review_audit"] is None
    session_service.resolve_billing_review(db, s.id, "confirm_normal_pricing", None, "fine by me", _manager(db))
    assert session_service.build_bill(s)["billing_review_audit"]["action"] == "confirm_normal_pricing"


def test_failed_resolution_rolls_back_every_related_change(db, device, monkeypatch):
    """Package terms, converted free items, fees, totals and the audit are written together or not at all."""
    user, table = _setup(db)
    manager = _manager(db)
    beer = make_product(db)
    s = flagged_session(db, device, table)
    session_service.add_item(db, s.id, beer.id, 3, None, user)
    s.start_time = T0
    session_lifecycle.finalize_stop(db, s, table, None, at=T0 + timedelta(minutes=90))
    pkg = make_package(db, items=[(beer.id, 2)])
    db.commit()
    snapshot = lambda: {
        "pkg": (s.package_id, s.package_name, s.package_price, s.package_snapshot),
        "items": sorted((i.quantity, i.from_package, i.product_name, i.total_price) for i in s.items),
        "money": (s.total_table_fee, s.total_product_fee, s.discount, s.grand_total),
        "review": (s.billing_review_state, s.billing_review_resolution, s.billing_review_note, s.billing_reviewed_by_id,
                   s.billing_reviewed_at, s.billing_review_audit, s.requested_package_id, s.billing_review_reason),
    }
    before = snapshot()
    assert before["pkg"] == (None, None, None, None) and before["review"][0] == "required"

    def boom(_session):
        raise RuntimeError("simulated failure after the package and items were changed")
    monkeypatch.setattr(session_lifecycle, "recompute_totals", boom)
    with pytest.raises(RuntimeError):
        session_service.resolve_billing_review(db, s.id, "assign_package", pkg.id, "voucher", manager)

    db.expire_all()                                                          # what the database really holds
    s = db.get(TableSession, s.id)
    assert snapshot() == before
    monkeypatch.undo()
    assert session_service.resolve_billing_review(db, s.id, "assign_package", pkg.id, "voucher", manager).package_name == "1h Combo"


def test_a_refused_resolution_leaves_the_session_untouched(db, device):
    user, table = _setup(db)
    s = flagged_session(db, device, table)
    s.payment_state = PaymentState.PENDING
    db.commit()
    with pytest.raises(HTTPException):
        session_service.resolve_billing_review(db, s.id, "confirm_normal_pricing", None, "too late", _manager(db))
    s = fresh(db, s)
    assert s.billing_review_state == BILLING_REVIEW_REQUIRED and s.billing_review_audit is None


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
