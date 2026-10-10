# tests/billiard/test_event_sessions.py
# Run from the project root:  python -m pytest app/tests/test_event_sessions.py -v
import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/billiard_test_import.db")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.init_db  # noqa: F401
from app.database import Base, get_db
from app.billiard.models import (
    BilliardDevice, BilliardTable, DeviceEvent, DeviceEventStatus, DeviceLocalIdMap,
    GameStatus, SessionStatus, TableGame, TableSession, TableStatus,
)
from app.billiard.routes.controller_router import router as controller_router
from app.billiard.schemas.event import DeviceEventIn
from app.billiard.services.device_auth import hash_api_key
from app.billiard.services.event_service import event_service
from app.billiard.services.game_service import game_service
from app.billiard.services.session_service import session_service
from app.billiard.services.table_service import table_service
from app.billiard.utils.billing import as_utc
from app.user.models.user import User


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, autoflush=False)()
    yield s
    s.close()


@pytest.fixture()
def env(db):
    user = User(client_id="c1", username="u1", email="u1@x.com", hashed_password="x")
    table = BilliardTable(name="T1", client_id="c1", hourly_rate=Decimal("100000"))
    device = BilliardDevice(client_id="c1", device_id="DEV1", name="ctrl", api_key_hash=hash_api_key("secret"))
    db.add_all([user, table, device])
    db.commit()
    return SimpleNamespace(user=user, table=table, device=device)


def E(seq, kind, data=None, event_id=None, **kw):
    return DeviceEventIn(event_id=event_id or f"e{seq}", event=kind, device_seq=seq, data=data or {}, **kw)


def all_sessions(db):
    return list(db.execute(select(TableSession)).scalars())


def local_map(db, kind, local_id):
    return db.execute(
        select(DeviceLocalIdMap).where(DeviceLocalIdMap.kind == kind, DeviceLocalIdMap.local_id == local_id)
    ).scalar_one_or_none()


def pos_start(db, env, with_game=False):
    session = table_service.start_session(db, env.table.id, env.user)
    game = game_service.start_game(db, session.id, env.user) if with_game else None
    db.commit()
    return session, game


# ── session_start ────────────────────────────────────────────────────────
def test_session_start_creates_session_with_device_time(db, env):
    start = datetime.now(timezone.utc) - timedelta(minutes=30)
    res = event_service.ingest(db, env.device, [
        E(1, "session_start", table_id=env.table.id, local_session_id="LOCAL-S-1",
          timestamp=start, clock_synced=True),
    ])
    assert res.accepted == ["e1"]
    (s,) = all_sessions(db)
    assert as_utc(s.start_time) == start
    assert s.start_time_source == "device" and s.opened_by_id is None
    assert s.hourly_rate == Decimal("100000") and s.billing_policy      # snapshots taken
    db.refresh(env.table)
    assert env.table.status == TableStatus.PLAYING
    assert local_map(db, "session", "LOCAL-S-1").session_id == s.id


def test_session_start_adopts_existing_server_session(db, env):
    server_session, _ = pos_start(db, env)
    res = event_service.ingest(db, env.device, [
        E(1, "session_start", table_id=env.table.id, local_session_id="LOCAL-S-1"),
    ])
    assert res.accepted == ["e1"]
    assert [s.id for s in all_sessions(db)] == [server_session.id]       # no duplicate
    assert local_map(db, "session", "LOCAL-S-1").session_id == server_session.id
    row = db.execute(select(DeviceEvent).where(DeviceEvent.event_id == "e1")).scalar_one()
    assert row.payload["reconciled"] == {"adopted_session_id": server_session.id}


def test_unsynced_clock_uses_server_time(db, env):
    res = event_service.ingest(db, env.device, [
        E(1, "session_start", table_id=env.table.id,
          timestamp=datetime.now(timezone.utc) - timedelta(hours=5), clock_synced=False),
    ])
    assert res.accepted == ["e1"]
    (s,) = all_sessions(db)
    assert s.start_time_source == "server"
    assert as_utc(s.start_time) > datetime.now(timezone.utc) - timedelta(minutes=1)


def test_slightly_future_device_time_is_clamped_to_now(db, env):
    """Within the 120s tolerance a timestamp is clock jitter: accepted, clamped to now."""
    before = datetime.now(timezone.utc)

    res = event_service.ingest(db, env.device, [
        E(1, "session_start", table_id=env.table.id,
          timestamp=before + timedelta(seconds=30), clock_synced=True),
    ])

    assert "e1" in res.accepted, res.rejected
    (s,) = all_sessions(db)
    start_time = as_utc(s.start_time)
    assert start_time <= datetime.now(timezone.utc)
    assert start_time >= before - timedelta(seconds=2)


def test_far_future_device_time_is_rejected(db, env):
    res = event_service.ingest(db, env.device, [
        E(1, "session_start", table_id=env.table.id,
          timestamp=datetime.now(timezone.utc) + timedelta(hours=3), clock_synced=True),
    ])

    assert [r.event_id for r in res.rejected] == ["e1"]
    assert "ahead of server time" in res.rejected[0].error
    assert not all_sessions(db)
    event = db.execute(select(DeviceEvent).where(DeviceEvent.event_id == "e1")).scalar_one()
    assert event.status == DeviceEventStatus.REJECTED


def test_duplicate_session_start_creates_one_session(db, env):
    ev = E(1, "session_start", table_id=env.table.id, local_session_id="LOCAL-S-1")
    event_service.ingest(db, env.device, [ev])
    res = event_service.ingest(db, env.device, [ev])
    assert res.duplicates == ["e1"] and len(all_sessions(db)) == 1


def test_session_start_on_maintenance_table_is_conflict(db, env):
    env.table.status = TableStatus.MAINTENANCE
    db.commit()
    res = event_service.ingest(db, env.device, [E(1, "session_start", table_id=env.table.id)])
    assert [c.event_id for c in res.conflicts] == ["e1"] and not all_sessions(db)

def test_session_start_accepts_5_hour_old_device_timestamp(db, env):
    start = datetime.now(timezone.utc) - timedelta(hours=5)

    res = event_service.ingest(db, env.device, [
        E(
            1,
            "session_start",
            table_id=env.table.id,
            timestamp=start,
            clock_synced=True,
        )
    ])

    assert res.accepted == ["e1"]
    assert not res.rejected

    (session,) = all_sessions(db)
    assert as_utc(session.start_time) == start
    assert session.start_time_source == "device"


def test_session_start_rejects_49_hour_old_device_timestamp(db, env):
    old_timestamp = datetime.now(timezone.utc) - timedelta(hours=49)

    res = event_service.ingest(db, env.device, [
        E(
            1,
            "session_start",
            table_id=env.table.id,
            timestamp=old_timestamp,
            clock_synced=True,
        )
    ])

    assert any(event.event_id == "e1" for event in res.rejected)
    assert not all_sessions(db)

    event = db.execute(
        select(DeviceEvent).where(DeviceEvent.event_id == "e1")
    ).scalar_one()

    assert event.status == DeviceEventStatus.REJECTED

# ── full offline replay ──────────────────────────────────────────────────
def test_full_offline_replay(db, env):
    base = datetime.now(timezone.utc)
    t0 = base - timedelta(minutes=120)
    sref = {"local_session_id": "LOCAL-S-1"}
    res = event_service.ingest(db, env.device, [
        E(1, "session_start", table_id=env.table.id, timestamp=t0, clock_synced=True, **sref),
        E(2, "game_start", local_game_id="LOCAL-G-1", timestamp=t0 + timedelta(seconds=1), clock_synced=True, **sref),
        E(3, "score_change", {"score_a": 5, "score_b": 3}, local_game_id="LOCAL-G-1"),
        E(4, "new_game", {"new_local_game_id": "LOCAL-G-2", "score_a": 5, "score_b": 3},
          local_game_id="LOCAL-G-1", timestamp=t0 + timedelta(minutes=40), clock_synced=True),
        E(5, "score_change", {"score_a": 7, "score_b": 4}, local_game_id="LOCAL-G-2"),
        E(6, "session_stop", timestamp=base - timedelta(minutes=30), clock_synced=True, **sref),
    ])
    assert res.accepted == [f"e{i}" for i in range(1, 7)] and not res.rejected and not res.conflicts
    assert res.server_state_version == 6

    (s,) = all_sessions(db)
    assert s.status == SessionStatus.COMPLETED
    assert s.duration_minutes == 90
    assert s.total_table_fee == Decimal("150000.00")        # computed by the SERVER
    assert s.end_time_source == "device"
    db.refresh(env.table)
    assert env.table.status == TableStatus.AVAILABLE

    g1, g2 = db.execute(select(TableGame).order_by(TableGame.game_number)).scalars().all()
    assert (g1.status, g1.player_a_score, g1.player_b_score) == (GameStatus.COMPLETED, 5, 3)
    assert (g2.status, g2.player_a_score, g2.player_b_score) == (GameStatus.COMPLETED, 7, 4)
    assert local_map(db, "game", "LOCAL-G-1").game_id == g1.id
    assert local_map(db, "game", "LOCAL-G-2").game_id == g2.id


# ── session_stop ─────────────────────────────────────────────────────────
def test_session_stop_on_completed_session_keeps_server_billing(db, env):
    session, _ = pos_start(db, env)
    session_service.stop_session(db, session.id, env.user)
    db.commit()
    before = (session.end_time, session.total_table_fee, session.grand_total)

    res = event_service.ingest(db, env.device, [E(1, "session_stop", {"session_id": session.id})])
    assert res.accepted == ["e1"]
    db.refresh(session)
    assert (session.end_time, session.total_table_fee, session.grand_total) == before


def test_session_stop_applies_final_scores_and_closes_game(db, env):
    session, game = pos_start(db, env, with_game=True)
    res = event_service.ingest(db, env.device, [
        E(1, "session_stop", {"score_a": 9, "score_b": 8}, table_id=env.table.id),
    ])
    assert res.accepted == ["e1"]
    db.refresh(session)
    db.refresh(game)
    assert session.status == SessionStatus.COMPLETED
    assert (game.status, game.player_a_score, game.player_b_score) == (GameStatus.COMPLETED, 9, 8)


def test_unknown_local_session_rejected(db, env):
    res = event_service.ingest(db, env.device, [E(1, "session_stop", local_session_id="LOCAL-S-404")])
    assert len(res.rejected) == 1
    assert db.execute(select(DeviceEvent).where(DeviceEvent.event_id == "e1")).scalar_one().status \
        == DeviceEventStatus.REJECTED


# ── game_start ───────────────────────────────────────────────────────────
def test_game_start_adopts_active_server_game(db, env):
    session, game = pos_start(db, env, with_game=True)
    res = event_service.ingest(db, env.device, [
        E(1, "game_start", table_id=env.table.id, local_game_id="LOCAL-G-1"),
    ])
    assert res.accepted == ["e1"]
    assert len(db.execute(select(TableGame)).scalars().all()) == 1
    assert local_map(db, "game", "LOCAL-G-1").game_id == game.id


def test_game_start_in_stopped_session_is_conflict(db, env):
    session, _ = pos_start(db, env)
    session_service.stop_session(db, session.id, env.user)
    db.commit()
    res = event_service.ingest(db, env.device, [E(1, "game_start", {"session_id": session.id})])
    assert [c.event_id for c in res.conflicts] == ["e1"]


# ── HTTP endpoints ───────────────────────────────────────────────────────
@pytest.fixture()
def client(db):
    app = FastAPI()
    app.include_router(controller_router)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


HEADERS = {"X-Device-Id": "DEV1", "X-Device-Key": "secret"}


def test_http_sync_applies_events(db, env, client):
    session, game = pos_start(db, env, with_game=True)
    body = {"device_id": "DEV1", "events": [
        {"event_id": "a", "event": "score_change", "device_seq": 1,
         "data": {"game_id": game.id, "score_a": 3, "score_b": 1}},
    ]}
    r = client.post("/billiard/controller/sync", json=body, headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["accepted"] == ["a"] and r.json()["server_state_version"] == 1
    db.refresh(game)
    assert (game.player_a_score, game.player_b_score) == (3, 1)


def test_http_rejects_bad_credentials_and_mismatched_device(env, client):
    body = {"device_id": "DEV1", "events": []}
    assert client.post("/billiard/controller/sync", json=body,
                       headers={**HEADERS, "X-Device-Key": "nope"}).status_code == 401
    assert client.post("/billiard/controller/sync", json={"device_id": "OTHER", "events": []},
                       headers=HEADERS).status_code == 403


def test_http_state_snapshot(db, env, client):
    session, game = pos_start(db, env, with_game=True)
    game_service.change_score(db, game.id, "A", 2, env.user)
    db.commit()
    r = client.get("/billiard/controller/state", headers=HEADERS)
    assert r.status_code == 200
    (t,) = r.json()["tables"]
    assert (t["table_id"], t["status"], t["session_id"], t["game_id"]) == (env.table.id, "playing", session.id, game.id)
    assert (t["player_a_score"], t["player_b_score"]) == (2, 0)