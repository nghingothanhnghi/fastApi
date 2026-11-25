# app/tests/test_table_status.py
# Roadmap item A: reserve / maintenance / release (status only, no reservation data).
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.tests._billiard_fixtures import *  # noqa: F401,F403
from app.billiard.models import TableStatus
from app.billiard.routes.table_router import router
from app.billiard.services import table_lifecycle
from app.billiard.services.session_service import session_service
from app.billiard.services.table_service import table_service
from app.database import Base, get_db
from app.user.utils.token import get_current_user


# ---------------------------------------------------------------- service

def _setup(db, client_id="c1"):
    user = make_user(db, client_id=client_id)
    table = make_table(db, client_id=client_id)
    db.commit()
    return user, table


def test_available_table_can_be_reserved_then_released(db):
    user, table = _setup(db)
    assert table_service.set_status(db, table.id, "reserve", user).status == TableStatus.RESERVED
    assert table_service.set_status(db, table.id, "release", user).status == TableStatus.AVAILABLE


def test_maintenance_blocks_start(db):
    user, table = _setup(db)
    table_service.set_status(db, table.id, "maintenance", user)
    with pytest.raises(HTTPException) as e:
        table_service.start_session(db, table.id, user)
    assert e.value.status_code == 409 and "maintenance" in e.value.detail


def test_reserved_table_cannot_start(db):
    user, table = _setup(db)
    table_service.set_status(db, table.id, "reserve", user)
    with pytest.raises(HTTPException) as e:
        table_service.start_session(db, table.id, user)
    assert e.value.status_code == 409 and "reserved" in e.value.detail


def test_maintenance_table_can_be_released_and_started(db):
    user, table = _setup(db)
    table_service.set_status(db, table.id, "maintenance", user)
    table_service.set_status(db, table.id, "release", user)
    assert table_service.start_session(db, table.id, user).table_id == table.id


def test_cannot_reserve_playing_table(db):
    user, table = _setup(db)
    table_service.start_session(db, table.id, user)
    db.commit()
    with pytest.raises(HTTPException) as e:
        table_service.set_status(db, table.id, "reserve", user)
    assert e.value.status_code == 409
    db.refresh(table)
    assert table.status == TableStatus.PLAYING        # unchanged


def test_cannot_set_status_on_inactive_table(db):
    user, table = _setup(db)
    table_service.deactivate_table(db, table.id, user)
    with pytest.raises(HTTPException) as e:
        table_service.set_status(db, table.id, "maintenance", user)
    assert e.value.status_code == 409 and "inactive" in e.value.detail


def test_reserve_twice_is_409(db):
    user, table = _setup(db)
    table_service.set_status(db, table.id, "reserve", user)
    with pytest.raises(HTTPException) as e:
        table_service.set_status(db, table.id, "reserve", user)
    assert e.value.status_code == 409


def test_reserved_table_can_go_straight_to_maintenance(db):
    user, table = _setup(db)
    table_service.set_status(db, table.id, "reserve", user)
    assert table_service.set_status(db, table.id, "maintenance", user).status == TableStatus.MAINTENANCE


def test_reserved_to_maintenance_ends_the_reservation_and_blocks_start(db):
    user, table = _setup(db)
    table_service.set_status(db, table.id, "reserve", user)
    table_service.set_status(db, table.id, "maintenance", user)
    with pytest.raises(HTTPException) as e:
        table_service.start_session(db, table.id, user)
    assert e.value.status_code == 409 and "maintenance" in e.value.detail
    # leaving maintenance gives a free table, not a reserved one
    assert table_service.set_status(db, table.id, "release", user).status == TableStatus.AVAILABLE


def test_maintenance_twice_is_409(db):
    user, table = _setup(db)
    table_service.set_status(db, table.id, "maintenance", user)
    with pytest.raises(HTTPException) as e:
        table_service.set_status(db, table.id, "maintenance", user)
    assert e.value.status_code == 409


def test_playing_table_cannot_enter_maintenance_until_session_is_stopped(db):
    user, table = _setup(db)
    s = table_service.start_session(db, table.id, user)
    db.commit()
    with pytest.raises(HTTPException) as e:
        table_service.set_status(db, table.id, "maintenance", user)
    assert e.value.status_code == 409
    db.refresh(table)
    assert table.status == TableStatus.PLAYING        # unchanged
    session_service.stop_session(db, s.id, user)
    db.commit()
    assert table_service.set_status(db, table.id, "maintenance", user).status == TableStatus.MAINTENANCE


def test_inactive_reserved_table_cannot_enter_maintenance(db):
    user, table = _setup(db)
    table_service.set_status(db, table.id, "reserve", user)
    table.is_active = False                           # e.g. changed outside this service
    db.flush()
    with pytest.raises(HTTPException) as e:
        table_service.set_status(db, table.id, "maintenance", user)
    assert e.value.status_code == 409 and "inactive" in e.value.detail


def test_release_available_table_is_409(db):
    user, table = _setup(db)
    with pytest.raises(HTTPException) as e:
        table_service.set_status(db, table.id, "release", user)
    assert e.value.status_code == 409


def test_release_playing_table_is_409(db):
    user, table = _setup(db)
    table_service.start_session(db, table.id, user)
    db.commit()
    with pytest.raises(HTTPException) as e:
        table_service.set_status(db, table.id, "release", user)
    assert e.value.status_code == 409


def test_other_tenant_gets_404(db):
    _, table = _setup(db, client_id="c1")
    other = make_user(db, client_id="c2", name="u2")
    with pytest.raises(HTTPException) as e:
        table_service.set_status(db, table.id, "reserve", other)
    assert e.value.status_code == 404


def test_unknown_table_is_404(db):
    user, _ = _setup(db)
    with pytest.raises(HTTPException) as e:
        table_service.set_status(db, 9999, "reserve", user)
    assert e.value.status_code == 404


def test_session_stop_after_maintenance_cycle_still_frees_table(db):
    user, table = _setup(db)
    table_service.set_status(db, table.id, "maintenance", user)
    table_service.set_status(db, table.id, "release", user)
    s = table_service.start_session(db, table.id, user)
    db.commit()
    session_service.stop_session(db, s.id, user)
    db.refresh(table)
    assert table.status == TableStatus.AVAILABLE


def test_find_inconsistencies_ignores_reserved_and_maintenance(db):
    user, table = _setup(db)
    table_service.set_status(db, table.id, "reserve", user)
    db.commit()
    assert table_lifecycle.find_inconsistencies(db) == []
    table_service.set_status(db, table.id, "release", user)
    table_service.set_status(db, table.id, "maintenance", user)
    db.commit()
    assert table_lifecycle.find_inconsistencies(db) == []


# ---------------------------------------------------------------- HTTP

def _http_user(role="manager", client_id="c1"):
    return SimpleNamespace(
        id=1, client_id=client_id, username="u",
        is_super_admin=lambda: False, has_role=lambda r: r == role,
    )


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    seed = Session()
    table = make_table(seed)
    seed.commit()
    table_id = table.id
    seed.close()

    app = FastAPI()
    app.include_router(router)

    def _db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    holder = {"u": _http_user()}
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: holder["u"]
    c = TestClient(app)
    c.table_id, c.holder = table_id, holder
    return c


def test_http_reserve_maintenance_release_roundtrip(client):
    t = client.table_id
    assert client.post(f"/tables/{t}/reserve").json()["status"] == "reserved"
    assert client.post(f"/tables/{t}/release").json()["status"] == "available"
    assert client.post(f"/tables/{t}/maintenance").json()["status"] == "maintenance"
    assert client.post(f"/tables/{t}/release").json()["status"] == "available"


def test_http_reserved_to_maintenance_allowed_for_manager_not_staff(client):
    t = client.table_id
    client.post(f"/tables/{t}/reserve")
    client.holder["u"] = _http_user("staff")
    assert client.post(f"/tables/{t}/maintenance").status_code == 403
    client.holder["u"] = _http_user("manager")
    assert client.post(f"/tables/{t}/maintenance").json()["status"] == "maintenance"


def test_http_playing_table_maintenance_message_says_stop_session(client):
    t = client.table_id
    client.post(f"/tables/{t}/start")
    r = client.post(f"/tables/{t}/maintenance")
    assert r.status_code == 409 and "stop its session" in r.json()["detail"]


def test_http_conflict_is_409(client):
    t = client.table_id
    client.post(f"/tables/{t}/reserve")
    assert client.post(f"/tables/{t}/reserve").status_code == 409


def test_http_staff_role_cannot_change_status(client):
    client.holder["u"] = _http_user("staff")
    t = client.table_id
    for action in ("reserve", "maintenance", "release"):
        assert client.post(f"/tables/{t}/{action}").status_code == 403


def test_http_other_tenant_404(client):
    client.holder["u"] = _http_user(client_id="other-club")
    assert client.post(f"/tables/{client.table_id}/reserve").status_code == 404
