# tests/billiard/test_event_service.py
# Run from the project root:  python -m pytest app/tests/test_event_service.py -v
import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/billiard_test_import.db")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import app.init_db  # noqa: F401
from app.database import Base
from app.billiard.models import (
    BilliardDevice, BilliardTable, DeviceEvent, DeviceEventStatus, GameStatus,
)
from app.billiard.schemas.event import DeviceEventIn
from app.billiard.services.device_auth import authenticate_device, hash_api_key
from app.billiard.services.event_service import event_service
from app.billiard.services.game_service import game_service
from app.billiard.services.table_service import table_service
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
    db.add(user)
    db.flush()
    table = BilliardTable(name="T1", client_id="c1", hourly_rate=Decimal("100000"))
    db.add(table)
    db.flush()
    session = table_service.start_session(db, table.id, user)
    game = game_service.start_game(db, session.id, user)
    device = BilliardDevice(client_id="c1", device_id="DEV1", name="ctrl", api_key_hash=hash_api_key("secret"))
    db.add(device)
    db.commit()
    return SimpleNamespace(user=user, table=table, session=session, game=game, device=device)


def E(seq, kind, data=None, event_id=None, **kw):
    return DeviceEventIn(event_id=event_id or f"e{seq}", event=kind, device_seq=seq, data=data or {}, **kw)


def scores(db, game):
    db.refresh(game)
    return game.player_a_score, game.player_b_score


def test_device_score_overrides_server_and_records_audit(db, env):
    game_service.change_score(db, env.game.id, "A", 1, env.user)   # POS says 1:0
    db.commit()
    res = event_service.ingest(db, env.device, [
        E(1, "score_change", {"game_id": env.game.id, "score_a": 8, "score_b": 6}),
    ])
    assert res.accepted == ["e1"] and not res.rejected and not res.conflicts
    assert scores(db, env.game) == (8, 6)
    row = db.execute(select(DeviceEvent).where(DeviceEvent.event_id == "e1")).scalar_one()
    assert row.status == DeviceEventStatus.PROCESSED
    assert row.payload["reconciled"] == {"server": [1, 0], "device": [8, 6]}


def test_duplicate_event_is_not_applied_twice(db, env):
    ref = {"game_id": env.game.id}
    event_service.ingest(db, env.device, [E(1, "score_change", {**ref, "score_a": 3, "score_b": 2})])
    res = event_service.ingest(db, env.device, [E(1, "score_change", {**ref, "score_a": 9, "score_b": 9})])
    assert res.duplicates == ["e1"] and not res.accepted
    assert scores(db, env.game) == (3, 2)


def test_ordered_by_seq_not_arrival_or_timestamp(db, env):
    ref = {"game_id": env.game.id}
    now = datetime.now(timezone.utc)
    res = event_service.ingest(db, env.device, [
        # arrives first, carries a LATER timestamp, but has the higher seq
        E(2, "score_change", {**ref, "score_a": 5, "score_b": 4}, timestamp=now + timedelta(hours=1)),
        E(1, "score_change", {**ref, "score_a": 1, "score_b": 0}, timestamp=now),
    ])
    assert res.accepted == ["e1", "e2"]
    assert scores(db, env.game) == (5, 4)
    assert res.server_state_version == 2


def test_unknown_game_rejected_and_stored(db, env):
    res = event_service.ingest(db, env.device, [E(1, "score_change", {"game_id": 9999, "score_a": 1, "score_b": 1})])
    assert [r.event_id for r in res.rejected] == ["e1"]
    row = db.execute(select(DeviceEvent).where(DeviceEvent.event_id == "e1")).scalar_one()
    assert row.status == DeviceEventStatus.REJECTED and row.error


def test_negative_or_missing_scores_rejected(db, env):
    ref = {"game_id": env.game.id}
    res = event_service.ingest(db, env.device, [
        E(1, "score_change", {**ref, "score_a": -1, "score_b": 0}),
        E(2, "score_change", ref),
    ])
    assert len(res.rejected) == 2 and not res.accepted
    assert scores(db, env.game) == (0, 0)
    assert res.server_state_version == 0       # nothing applied, nothing to discard


def test_other_tenants_game_rejected(db, env):
    other = BilliardDevice(client_id="c2", device_id="DEV2", name="x", api_key_hash=hash_api_key("k2"))
    db.add(other)
    db.commit()
    res = event_service.ingest(db, other, [E(1, "score_change", {"game_id": env.game.id, "score_a": 7, "score_b": 7})])
    assert len(res.rejected) == 1
    assert scores(db, env.game) == (0, 0)


def test_cancelled_game_is_a_conflict(db, env):
    env.game.status = GameStatus.CANCELLED
    db.commit()
    res = event_service.ingest(db, env.device, [E(1, "score_change", {"game_id": env.game.id, "score_a": 1, "score_b": 1})])
    assert [c.event_id for c in res.conflicts] == ["e1"]
    row = db.execute(select(DeviceEvent).where(DeviceEvent.event_id == "e1")).scalar_one()
    assert row.status == DeviceEventStatus.CONFLICT


def test_score_reset(db, env):
    ref = {"game_id": env.game.id}
    event_service.ingest(db, env.device, [
        E(1, "score_change", {**ref, "score_a": 4, "score_b": 4}),
        E(2, "score_reset", ref),
    ])
    assert scores(db, env.game) == (0, 0)


def test_game_end_applies_final_score_and_closes(db, env):
    res = event_service.ingest(db, env.device, [
        E(1, "game_end", {"game_id": env.game.id, "score_a": 10, "score_b": 7}),
    ])
    assert res.accepted == ["e1"]
    db.refresh(env.game)
    assert env.game.status == GameStatus.COMPLETED and env.game.end_time is not None
    assert scores(db, env.game) == (10, 7)


def test_game_resolved_from_table_when_no_id_given(db, env):
    res = event_service.ingest(db, env.device, [
        E(1, "score_change", {"score_a": 2, "score_b": 1}, table_id=env.table.id),
    ])
    assert res.accepted == ["e1"]
    assert scores(db, env.game) == (2, 1)


def test_unimplemented_event_type_rejected_not_dropped(db, env):
    res = event_service.ingest(db, env.device, [E(1, "session_start", table_id=env.table.id)])
    assert len(res.rejected) == 1
    assert db.execute(select(DeviceEvent).where(DeviceEvent.event_id == "e1")).scalar_one()


def test_server_state_version_is_contiguous_prefix(db, env):
    ref = {"game_id": env.game.id, "score_a": 1, "score_b": 1}
    res = event_service.ingest(db, env.device, [
        E(1, "score_change", ref),
        E(2, "score_change", {"game_id": 9999, "score_a": 1, "score_b": 1}),   # rejected
        E(3, "score_change", ref),                                             # applied, but after a gap
    ])
    assert res.server_state_version == 1


def test_heartbeat_updates_last_seen(db, env):
    res = event_service.ingest(db, env.device, [E(1, "heartbeat")])
    assert res.accepted == ["e1"]
    db.refresh(env.device)
    assert env.device.last_seen is not None


def test_authentication(db, env):
    assert authenticate_device(db, "DEV1", "secret").id == env.device.id
    for bad in (("DEV1", "wrong"), ("NOPE", "secret"), ("DEV1", "")):
        with pytest.raises(HTTPException) as e:
            authenticate_device(db, *bad)
        assert e.value.status_code == 401