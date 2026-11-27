# app/tests/test_device_watchdog.py
# Roadmap item H: the watchdog records online <-> offline changes of the controller.
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.tests.test_event_sessions import E, db, env  # noqa: F401  (db / env are fixtures)
from app.billiard import config
from app.billiard.jobs import device_watchdog_job as job_module
from app.billiard.models import BilliardDevice, DeviceStatus, DeviceStatusLog
from app.billiard.routes.controller_router import router as controller_router
from app.billiard.services import device_alerts, device_watchdog
from app.billiard.services.device_auth import authenticate_device, hash_api_key
from app.billiard.services.device_service import device_service
from app.billiard.services.event_service import event_service
from app.billiard.utils.billing import as_utc
from app.database import get_db
from app.user.models.user import User

NOW = datetime(2026, 11, 27, 3, 0, 0, tzinfo=timezone.utc)
REPO = Path(__file__).resolve().parents[2]


def set_device(db, device, status, silent_seconds):
    device.status = status
    device.last_seen = None if silent_seconds is None else NOW - timedelta(seconds=silent_seconds)
    device.status_changed_at = None
    db.commit()
    return device


def logs(db):
    db.expire_all()
    return list(db.execute(select(DeviceStatusLog).order_by(DeviceStatusLog.id)).scalars())


def fresh_device(db, device):
    db.expire_all()
    return db.get(BilliardDevice, device.id)


def add_device(db, client_id, device_id, status, silent_seconds):
    d = BilliardDevice(client_id=client_id, device_id=device_id, name=device_id, api_key_hash=hash_api_key("k"))
    db.add(d)
    db.flush()
    return set_device(db, d, status, silent_seconds)


# ---------------------------------------------------------------- sweep

def test_stale_device_is_marked_offline_and_logged(db, env):
    set_device(db, env.device, DeviceStatus.ONLINE, 120)
    switched = device_watchdog.sweep_offline(db, NOW)
    db.commit()
    assert [d.device_id for d in switched] == ["DEV1"]
    d = fresh_device(db, env.device)
    assert d.status == DeviceStatus.OFFLINE and as_utc(d.status_changed_at) == NOW
    [row] = logs(db)
    assert (row.device_id, row.from_status, row.to_status, as_utc(row.at)) == (d.id, "online", "offline", NOW)
    assert "120s" in row.reason


def test_fresh_device_stays_online(db, env):
    set_device(db, env.device, DeviceStatus.ONLINE, 10)
    assert device_watchdog.sweep_offline(db, NOW) == []
    db.commit()
    assert fresh_device(db, env.device).status == DeviceStatus.ONLINE and logs(db) == []


def test_sweep_is_idempotent(db, env):
    set_device(db, env.device, DeviceStatus.ONLINE, 500)
    assert len(device_watchdog.sweep_offline(db, NOW)) == 1
    db.commit()
    assert device_watchdog.sweep_offline(db, NOW + timedelta(seconds=30)) == []
    db.commit()
    assert len(logs(db)) == 1


def test_two_workers_log_one_transition(db, env):
    set_device(db, env.device, DeviceStatus.ONLINE, 500)
    other = sessionmaker(bind=db.get_bind())()
    try:
        first = device_watchdog.sweep_offline(db, NOW)
        second = device_watchdog.sweep_offline(other, NOW)        # sees the change already made
        db.commit()
        other.commit()
    finally:
        other.close()
    assert len(first) == 1 and second == [] and len(logs(db)) == 1


def test_sweep_only_touches_expired_devices_boundary(db, env):
    exactly = add_device(db, "c1", "AT90", DeviceStatus.ONLINE, 90)        # exactly the threshold: still online
    over = add_device(db, "c1", "AT91", DeviceStatus.ONLINE, 91)
    fresh = add_device(db, "c1", "AT5", DeviceStatus.ONLINE, 5)
    already = add_device(db, "c1", "OFF", DeviceStatus.OFFLINE, 900)       # stored offline: nothing to record
    never = add_device(db, "c1", "NEVER", DeviceStatus.ONLINE, None)       # online without a last_seen
    switched = {d.device_id for d in device_watchdog.sweep_offline(db, NOW)}
    db.commit()
    assert switched == {"AT91", "NEVER"}
    assert {fresh_device(db, d).status for d in (exactly, fresh)} == {DeviceStatus.ONLINE}
    assert fresh_device(db, already).status == DeviceStatus.OFFLINE
    assert {r.device_id for r in logs(db)} == {over.id, never.id}
    assert fresh_device(db, exactly).status_changed_at is None


def test_boundary_matches_effective_status(db, env, monkeypatch):
    """The stored status and what GET /status shows must use the same rule and the same threshold."""
    d = env.device
    d.status, d.last_seen = DeviceStatus.ONLINE, datetime.now(timezone.utc) - timedelta(seconds=89)
    assert device_service.effective_status(d) == DeviceStatus.ONLINE
    d.last_seen = datetime.now(timezone.utc) - timedelta(seconds=95)
    assert device_service.effective_status(d) == DeviceStatus.OFFLINE
    monkeypatch.setattr(config, "OFFLINE_AFTER_SECONDS", 300)
    assert device_service.effective_status(d) == DeviceStatus.ONLINE


def test_threshold_is_configurable(db, env, monkeypatch):
    set_device(db, env.device, DeviceStatus.ONLINE, 120)
    monkeypatch.setattr(config, "OFFLINE_AFTER_SECONDS", 300)
    assert device_watchdog.sweep_offline(db, NOW) == []                      # 120 s is fine under 300 s
    monkeypatch.setattr(config, "OFFLINE_AFTER_SECONDS", 60)
    assert len(device_watchdog.sweep_offline(db, NOW)) == 1
    db.rollback()
    set_device(db, env.device, DeviceStatus.ONLINE, 120)
    assert device_watchdog.sweep_offline(db, NOW, after=timedelta(seconds=600)) == []   # explicit override


# ---------------------------------------------------------------- coming back online

def test_heartbeat_brings_device_back_online_and_logs(db, env):
    set_device(db, env.device, DeviceStatus.ONLINE, 500)
    device_watchdog.sweep_offline(db, NOW)
    db.commit()
    before = datetime.now(timezone.utc) - timedelta(seconds=1)
    event_service.ingest(db, fresh_device(db, env.device), [E(1, "heartbeat", {"firmware_version": "1.0"})])
    d = fresh_device(db, env.device)
    assert d.status == DeviceStatus.ONLINE and d.status_changed_at is not None
    rows = logs(db)
    assert [(r.from_status, r.to_status) for r in rows] == [("online", "offline"), ("offline", "online")]
    assert as_utc(d.last_seen) >= before and as_utc(d.status_changed_at) >= before


def test_any_authenticated_contact_brings_it_back_online_once(db, env):
    set_device(db, env.device, DeviceStatus.OFFLINE, 500)
    authenticate_device(db, "DEV1", "secret")
    db.commit()
    authenticate_device(db, "DEV1", "secret")                                # already online: no second row
    event_service.ingest(db, fresh_device(db, env.device), [E(1, "heartbeat")])
    rows = logs(db)
    assert [(r.from_status, r.to_status) for r in rows] == [("offline", "online")]


def test_contact_while_online_writes_no_log_and_no_status_change_time(db, env):
    set_device(db, env.device, DeviceStatus.ONLINE, 5)
    authenticate_device(db, "DEV1", "secret")
    db.commit()
    assert logs(db) == [] and fresh_device(db, env.device).status_changed_at is None


def test_two_requests_log_one_online_transition(db, env):
    set_device(db, env.device, DeviceStatus.OFFLINE, 500)
    other = sessionmaker(bind=db.get_bind())()
    try:
        a = db.get(BilliardDevice, env.device.id)
        b = other.get(BilliardDevice, env.device.id)                         # both loaded it while offline
        assert device_watchdog.mark_online(db, a) is True
        assert device_watchdog.mark_online(other, b) is False                # lost the conditional update
        db.commit()
        other.commit()
    finally:
        other.close()
    assert len(logs(db)) == 1


def test_a_heartbeat_between_select_and_update_beats_the_sweep(db, env, monkeypatch):
    """The sweep picked the device as stale, then a heartbeat landed. The UPDATE re-checks last_seen and loses."""
    set_device(db, env.device, DeviceStatus.ONLINE, 500)
    real_execute, state = db.execute, {"selected": False}

    def execute(stmt, *a, **k):
        result = real_execute(stmt, *a, **k)
        if not state["selected"]:                                            # right after the candidate SELECT
            state["selected"] = True
            real_execute(text("UPDATE billiard_devices SET last_seen = :t"), {"t": NOW.strftime("%Y-%m-%d %H:%M:%S.%f")})   # string: the sqlite3 datetime adapter is deprecated
        return result
    monkeypatch.setattr(db, "execute", execute)
    assert device_watchdog.sweep_offline(db, NOW + timedelta(seconds=10)) == []
    monkeypatch.undo()
    db.commit()
    assert fresh_device(db, env.device).status == DeviceStatus.ONLINE and logs(db) == []


def test_a_sweep_that_already_lost_logs_nothing_for_a_device_that_went_offline_meanwhile(db, env, monkeypatch):
    """Another worker switched it between our SELECT and UPDATE: rowcount 0, so no duplicate log row."""
    set_device(db, env.device, DeviceStatus.ONLINE, 500)
    real_execute, state = db.execute, {"selected": False}

    def execute(stmt, *a, **k):
        result = real_execute(stmt, *a, **k)
        if not state["selected"]:
            state["selected"] = True
            real_execute(text("UPDATE billiard_devices SET status = 'offline'"))
        return result
    monkeypatch.setattr(db, "execute", execute)
    assert device_watchdog.sweep_offline(db, NOW) == []
    monkeypatch.undo()
    assert logs(db) == []


# ---------------------------------------------------------------- alert hook and job

@pytest.fixture()
def job(db, monkeypatch):
    monkeypatch.setattr(job_module, "SessionLocal", lambda: db)
    calls = []
    monkeypatch.setattr(device_alerts, "notify_device_offline", lambda d: calls.append(d.device_id))
    return calls


def silent_for(db, device, seconds):
    set_device(db, device, DeviceStatus.ONLINE, 0)
    device.last_seen = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    db.commit()


def test_alert_hook_called_once_per_transition(db, env, job):
    silent_for(db, env.device, 500)
    job_module.device_watchdog_job()
    job_module.device_watchdog_job()                                         # nothing new on the second run
    assert job == ["DEV1"] and len(logs(db)) == 1
    event_service.ingest(db, fresh_device(db, env.device), [E(1, "heartbeat")])
    silent_for(db, fresh_device(db, env.device), 500)                        # goes silent again: a NEW transition
    job_module.device_watchdog_job()
    assert job == ["DEV1", "DEV1"]


def test_no_alert_for_a_healthy_device(db, env, job):
    silent_for(db, env.device, 5)
    job_module.device_watchdog_job()
    assert job == [] and logs(db) == []


def test_alert_failure_does_not_undo_or_repeat_the_change(db, env, monkeypatch):
    monkeypatch.setattr(job_module, "SessionLocal", lambda: db)
    attempts = []
    def broken(device):
        attempts.append(device.device_id)
        raise RuntimeError("pager is down")
    monkeypatch.setattr(device_alerts, "notify_device_offline", broken)
    silent_for(db, env.device, 500)
    job_module.device_watchdog_job()                                         # must not raise
    job_module.device_watchdog_job()
    assert attempts == ["DEV1"]
    assert fresh_device(db, env.device).status == DeviceStatus.OFFLINE and len(logs(db)) == 1


def test_a_failing_sweep_rolls_back_and_does_not_crash_the_scheduler(db, env, job, monkeypatch):
    silent_for(db, env.device, 500)
    device_pk = env.device.id                                                # the job closes the session
    real = device_watchdog.sweep_offline
    def boom(session, *a, **k):
        real(session, *a, **k)                                               # writes, then fails
        raise RuntimeError("db went away")
    monkeypatch.setattr(device_watchdog, "sweep_offline", boom)
    job_module.device_watchdog_job()                                         # logged, not raised
    assert job == []
    db.expire_all()
    assert db.get(BilliardDevice, device_pk).status == DeviceStatus.ONLINE and logs(db) == []


def test_alert_hook_logs_a_warning(env, caplog):
    with caplog.at_level("WARNING"):
        device_alerts.notify_device_offline(env.device)
    assert "DEV1" in caplog.text and "offline" in caplog.text


def test_job_is_registered_in_main():
    source = (REPO / "main.py").read_text(encoding="utf-8")
    assert "device_watchdog_job" in source and "billiard_device_watchdog_job" in source


# ---------------------------------------------------------------- GET /controller/status

def status_client(db, club):
    app = FastAPI()
    app.include_router(controller_router)
    from app.user.utils.token import get_current_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, client_id=club, username="boss", is_super_admin=lambda: False, has_role=lambda r: True)
    return TestClient(app)


def test_status_endpoint_returns_the_last_change_time(db, env):
    set_device(db, env.device, DeviceStatus.ONLINE, 500)
    device_watchdog.sweep_offline(db, NOW)
    db.commit()
    [row] = status_client(db, "c1").get("/billiard/controller/status").json()
    assert row["status"] == "offline" and row["status_changed_at"].startswith("2026-11-27T03:00:00")


def test_status_endpoint_never_shows_another_club(db, env):
    add_device(db, "c2", "OTHER", DeviceStatus.ONLINE, 500)
    device_watchdog.sweep_offline(db, NOW)                                   # the job is global ...
    db.commit()
    assert [r["device_id"] for r in status_client(db, "c1").get("/billiard/controller/status").json()] == ["DEV1"]
    assert [r["device_id"] for r in status_client(db, "c2").get("/billiard/controller/status").json()] == ["OTHER"]


# ---------------------------------------------------------------- migration

def test_migration_is_idempotent_on_an_old_database(tmp_path):
    path = tmp_path / "old.db"
    old = create_engine(f"sqlite:///{path}")
    with old.begin() as c:
        c.execute(text("CREATE TABLE billiard_devices (id INTEGER PRIMARY KEY, device_id TEXT, status TEXT)"))
        c.execute(text("INSERT INTO billiard_devices VALUES (1, 'D', 'online')"))
    old.dispose()
    env_vars = {**os.environ, "DATABASE_URL": f"sqlite:///{path}", "SECRET_KEY": "test"}
    for _ in range(2):
        done = subprocess.run([sys.executable, "migrate_billiard_device_watchdog.py"], cwd=REPO, env=env_vars,
                              capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
    check = create_engine(f"sqlite:///{path}")
    with check.connect() as c:
        cols = {r[1] for r in c.execute(text("PRAGMA table_info(billiard_devices)"))}
        tables = {r[0] for r in c.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        assert "status_changed_at" in cols and "billiard_device_status_log" in tables
        assert c.execute(text("SELECT status FROM billiard_devices")).scalar() == "online"   # data kept
    check.dispose()
