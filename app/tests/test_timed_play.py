# app/tests/test_timed_play.py
# Roadmap item D: timed play. ends_at is a countdown + overtime flag only; billing never uses it.
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
from app.billiard.models import BilliardDevice, SessionStatus
from app.billiard.routes.session_router import router as session_router
from app.billiard.routes.table_router import router as table_router
from app.billiard.schemas.session import ExtendSessionRequest, StartSessionRequest
from app.billiard.services import session_lifecycle
from app.billiard.services.device_auth import hash_api_key
from app.billiard.services.device_service import device_service
from app.billiard.services.session_service import session_service
from app.billiard.services.table_service import table_service
from app.database import Base, get_db
from app.user.utils.token import get_current_user

D = Decimal


def _utc(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _setup(db, client_id="c1", name="u1"):
    user = make_user(db, client_id=client_id, name=name)
    table = make_table(db, client_id=client_id)
    db.commit()
    return user, table


def _row(db, user, session_id):
    return next(r for r in table_service.get_active_tables(db, user) if r["session_id"] == session_id)


# ---------------------------------------------------------------- start

def test_start_without_planned_minutes_has_no_ends_at(db):
    user, table = _setup(db)
    s = table_service.start_session(db, table.id, user)
    assert s.ends_at is None
    row = _row(db, user, s.id)
    assert row["ends_at"] is None and row["remaining_seconds"] is None and row["is_overtime"] is False


def test_start_with_planned_minutes_sets_ends_at(db):
    user, table = _setup(db)
    s = table_service.start_session(db, table.id, user, planned_minutes=60)
    assert _utc(s.ends_at) - _utc(s.start_time) == timedelta(minutes=60)


def test_bad_planned_minutes_is_409_and_leaves_the_table_free(db):
    user, table = _setup(db)
    for bad in (0, -5, 1441):
        with pytest.raises(HTTPException) as e:
            table_service.start_session(db, table.id, user, planned_minutes=bad)
        assert e.value.status_code == 409
    db.refresh(table)
    assert table.status.value == "available"


# ---------------------------------------------------------------- extend

def test_extend_adds_minutes_to_ends_at(db):
    user, table = _setup(db)
    s = table_service.start_session(db, table.id, user, planned_minutes=60)
    before = _utc(s.ends_at)
    session_service.extend_session(db, s.id, 30, user)
    assert _utc(s.ends_at) - before == timedelta(minutes=30)


def test_extend_without_ends_at_starts_from_now(db):
    user, table = _setup(db)
    s = table_service.start_session(db, table.id, user)             # open play
    t0 = datetime.now(timezone.utc)
    session_service.extend_session(db, s.id, 30, user)
    assert t0 + timedelta(minutes=30) <= _utc(s.ends_at) <= datetime.now(timezone.utc) + timedelta(minutes=30)


def test_extend_after_ends_at_passed_gives_the_full_minutes_from_now(db):
    user, table = _setup(db)
    s = table_service.start_session(db, table.id, user, planned_minutes=30)
    s.start_time = datetime.now(timezone.utc) - timedelta(hours=2)
    s.ends_at = datetime.now(timezone.utc) - timedelta(minutes=90)  # 90 minutes overdue
    db.commit()
    assert _row(db, user, s.id)["is_overtime"] is True
    session_service.extend_session(db, s.id, 30, user)
    remaining = (_utc(s.ends_at) - datetime.now(timezone.utc)).total_seconds()
    assert 29 * 60 < remaining <= 30 * 60                           # not still in the past
    assert _row(db, user, s.id)["is_overtime"] is False


def test_extend_twice_accumulates(db):
    user, table = _setup(db)
    s = table_service.start_session(db, table.id, user, planned_minutes=60)
    before = _utc(s.ends_at)
    session_service.extend_session(db, s.id, 15, user)
    session_service.extend_session(db, s.id, 15, user)
    assert _utc(s.ends_at) - before == timedelta(minutes=30)


def test_extend_completed_session_is_409(db):
    user, table = _setup(db)
    s = table_service.start_session(db, table.id, user, planned_minutes=60)
    session_service.stop_session(db, s.id, user)
    db.commit()
    with pytest.raises(HTTPException) as e:
        session_service.extend_session(db, s.id, 30, user)
    assert e.value.status_code == 409


def test_extend_cancelled_session_is_409(db):
    user, table = _setup(db)
    s = table_service.start_session(db, table.id, user, planned_minutes=60)
    session_service.cancel_session(db, s.id, "opened by mistake", user)
    db.commit()
    with pytest.raises(HTTPException) as e:
        session_service.extend_session(db, s.id, 30, user)
    assert e.value.status_code == 409


def test_extend_other_tenant_404(db):
    user, table = _setup(db)
    s = table_service.start_session(db, table.id, user, planned_minutes=60)
    db.commit()
    other = make_user(db, client_id="c2", name="u2")
    with pytest.raises(HTTPException) as e:
        session_service.extend_session(db, s.id, 30, other)
    assert e.value.status_code == 404


def test_extend_limits_are_rejected():
    for bad in (0, -1, 481):
        with pytest.raises(ValidationError):
            ExtendSessionRequest(minutes=bad)
    for bad in (0, -1, 1441):
        with pytest.raises(ValidationError):
            StartSessionRequest(planned_minutes=bad)
    assert ExtendSessionRequest(minutes=480).minutes == 480 and StartSessionRequest().planned_minutes is None


def test_extend_lifecycle_guards_its_own_limits(db):
    user, table = _setup(db)
    s = table_service.start_session(db, table.id, user)
    with pytest.raises(ValueError):
        session_lifecycle.extend_session(s, 0)
    with pytest.raises(ValueError):
        session_lifecycle.extend_session(s, 1441)


# ---------------------------------------------------------------- the board

def test_board_shows_remaining_time_and_no_overtime_before_ends_at(db):
    user, table = _setup(db)
    s = table_service.start_session(db, table.id, user, planned_minutes=60)
    row = _row(db, user, s.id)
    assert row["is_overtime"] is False
    assert 59 * 60 <= row["remaining_seconds"] <= 60 * 60
    assert _utc(row["ends_at"]) == _utc(s.ends_at)


def test_overtime_flag_after_ends_at(db):
    user, table = _setup(db)
    s = table_service.start_session(db, table.id, user, planned_minutes=30)
    s.start_time = datetime.now(timezone.utc) - timedelta(minutes=45)
    s.ends_at = datetime.now(timezone.utc) - timedelta(minutes=15)
    db.commit()
    row = _row(db, user, s.id)
    assert row["is_overtime"] is True and row["remaining_seconds"] < 0
    assert -15 * 60 - 5 <= row["remaining_seconds"] <= -15 * 60 + 5


def test_server_never_stops_a_session_by_itself(db):
    user, table = _setup(db)
    s = table_service.start_session(db, table.id, user, planned_minutes=30)
    s.ends_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.commit()
    table_service.get_active_tables(db, user)
    db.refresh(s)
    assert s.status == SessionStatus.ACTIVE and s.end_time is None


# ---------------------------------------------------------------- billing is untouched

def _stopped_fee(db, planned):
    user, table = _setup(db, client_id=f"club-{planned}", name=f"user-{planned}")
    s = table_service.start_session(db, table.id, user, planned_minutes=planned)
    s.start_time = datetime.now(timezone.utc) - timedelta(minutes=90, seconds=10)   # real play: 91 min
    db.commit()
    return session_service.stop_session(db, s.id, user)


def test_billing_ignores_ends_at(db):
    open_play = _stopped_fee(db, None)
    short_plan = _stopped_fee(db, 30)       # stopped long after its planned end
    long_plan = _stopped_fee(db, 240)       # stopped long before its planned end
    assert open_play.duration_minutes == short_plan.duration_minutes == long_plan.duration_minutes
    assert open_play.total_table_fee == short_plan.total_table_fee == long_plan.total_table_fee > 0


def test_extending_does_not_change_the_fee(db):
    user, table = _setup(db)
    s = table_service.start_session(db, table.id, user, planned_minutes=30)
    s.start_time = datetime.now(timezone.utc) - timedelta(minutes=45, seconds=10)
    session_service.extend_session(db, s.id, 120, user)
    db.commit()
    stopped = session_service.stop_session(db, s.id, user)
    assert stopped.duration_minutes == 46


def test_bill_shows_ends_at_for_information(db):
    user, table = _setup(db)
    s = table_service.start_session(db, table.id, user, planned_minutes=60)
    assert session_service.build_bill(s)["ends_at"] == s.ends_at
    stopped = session_service.stop_session(db, s.id, user)
    assert session_service.build_bill(stopped)["ends_at"] is not None


# ---------------------------------------------------------------- controller

def test_controller_state_contains_ends_at(db):
    user, table = _setup(db)
    s = table_service.start_session(db, table.id, user, planned_minutes=60)
    device = BilliardDevice(client_id="c1", device_id="DEV1", name="ctrl", api_key_hash=hash_api_key("k"))
    db.add(device)
    db.commit()
    state = device_service.build_state(db, device)
    t = next(x for x in state.tables if x.table_id == table.id)
    assert t.session_id == s.id and _utc(t.session_ends_at) == _utc(s.ends_at)
    session_service.extend_session(db, s.id, 30, user)
    db.commit()
    t2 = next(x for x in device_service.build_state(db, device).tables if x.table_id == table.id)
    assert _utc(t2.session_ends_at) - _utc(t.session_ends_at) == timedelta(minutes=30)


# ---------------------------------------------------------------- HTTP

def _http_user(role="staff", client_id="c1"):
    return SimpleNamespace(
        id=1, client_id=client_id, username="cashier",
        is_super_admin=lambda: False, has_role=lambda r: r == role,
    )


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    seed = Session()
    make_user(seed)
    table = make_table(seed)
    seed.commit()
    tid = table.id
    seed.close()

    app = FastAPI()
    app.include_router(table_router)
    app.include_router(session_router)

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
    c.tid, c.holder = tid, holder
    return c


def test_http_start_without_body_still_works(client):
    r = client.post(f"/tables/{client.tid}/start")
    assert r.status_code == 200, r.text
    assert r.json()["ends_at"] is None


def test_http_start_with_planned_minutes_returns_ends_at(client):
    r = client.post(f"/tables/{client.tid}/start", json={"planned_minutes": 60})
    assert r.status_code == 200, r.text
    assert r.json()["ends_at"] is not None


def test_http_start_with_empty_object_is_open_play(client):
    r = client.post(f"/tables/{client.tid}/start", json={})
    assert r.status_code == 200 and r.json()["ends_at"] is None


def test_http_start_with_bad_planned_minutes_is_422(client):
    for bad in (0, -1, 1441, "abc"):
        assert client.post(f"/tables/{client.tid}/start", json={"planned_minutes": bad}).status_code == 422


def test_http_extend_returns_the_bill_with_the_new_ends_at(client):
    sid = client.post(f"/tables/{client.tid}/start", json={"planned_minutes": 60}).json()["session_id"]
    first = client.get(f"/sessions/{sid}").json()["ends_at"]
    r = client.post(f"/sessions/{sid}/extend", json={"minutes": 30})
    assert r.status_code == 200, r.text
    new = datetime.fromisoformat(r.json()["ends_at"])
    old = datetime.fromisoformat(first)
    assert new - old == timedelta(minutes=30)


def test_http_extend_is_open_to_staff(client):
    sid = client.post(f"/tables/{client.tid}/start").json()["session_id"]
    assert client.holder["u"].has_role("staff")
    assert client.post(f"/sessions/{sid}/extend", json={"minutes": 15}).status_code == 200


def test_http_extend_validation_is_422(client):
    sid = client.post(f"/tables/{client.tid}/start").json()["session_id"]
    for body in ({}, {"minutes": 0}, {"minutes": -5}, {"minutes": 481}, {"minutes": "x"}):
        assert client.post(f"/sessions/{sid}/extend", json=body).status_code == 422


def test_http_extend_completed_session_is_409(client):
    sid = client.post(f"/tables/{client.tid}/start").json()["session_id"]
    client.post(f"/sessions/{sid}/stop")
    assert client.post(f"/sessions/{sid}/extend", json={"minutes": 15}).status_code == 409


def test_http_extend_other_tenant_404(client):
    sid = client.post(f"/tables/{client.tid}/start").json()["session_id"]
    client.holder["u"] = _http_user(client_id="other-club")
    assert client.post(f"/sessions/{sid}/extend", json={"minutes": 15}).status_code == 404


def test_http_board_shows_the_countdown(client):
    client.post(f"/tables/{client.tid}/start", json={"planned_minutes": 60})
    rows = client.get("/tables/active").json()
    assert len(rows) == 1 and rows[0]["is_overtime"] is False and rows[0]["remaining_seconds"] > 3500
