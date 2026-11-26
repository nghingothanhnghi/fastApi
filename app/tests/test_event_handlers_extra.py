# app/tests/test_event_handlers_extra.py
# Roadmap item G: time_extend, table_status, button_press, device_error controller events.
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.tests.test_event_sessions import E, db, env, pos_start  # noqa: F401  (db / env are fixtures)
from app.billiard.models import (
    BilliardDevice, BilliardPackage, BilliardPackageItem, BilliardTable, DeviceEvent, DeviceEventStatus,
    SessionStatus, TableSession, TableStatus,
)
from app.billiard.routes.controller_router import router as controller_router
from app.billiard.services import session_lifecycle
from app.billiard.services.event_service import BUTTON_ACTIONS, event_service
from app.billiard.services.session_service import session_service
from app.billiard.services.table_service import table_service
from app.billiard.utils.billing import as_utc
from app.database import get_db
from app.product.models.product import Product
from app.user.models.user import User


def run(db, env, *events):
    return event_service.ingest(db, env.device, list(events))


def event_row(db, event_id):
    return db.execute(select(DeviceEvent).where(DeviceEvent.event_id == event_id)).scalar_one()


def fresh(db, obj):
    db.expire_all()
    return db.get(type(obj), obj.id)


# ---------------------------------------------------------------- time_extend

def test_time_extend_event_extends_ends_at(db, env):
    session, _ = pos_start(db, env)
    session.ends_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    db.commit()
    before = as_utc(session.ends_at)
    res = run(db, env, E(1, "time_extend", {"minutes": 30}, table_id=env.table.id))
    assert res.accepted == ["e1"]
    assert as_utc(fresh(db, session).ends_at) == before + timedelta(minutes=30)
    assert event_row(db, "e1").payload["reconciled"]["ends_at"]


def test_time_extend_on_open_play_sets_ends_at_from_now(db, env):
    session, _ = pos_start(db, env)
    res = run(db, env, E(1, "time_extend", {"minutes": 15}, table_id=env.table.id))
    assert res.accepted == ["e1"]
    left = (as_utc(fresh(db, session).ends_at) - datetime.now(timezone.utc)).total_seconds()
    assert 14 * 60 < left <= 15 * 60


def test_time_extend_uses_the_device_press_time_as_base(db, env):
    """A press made 2 hours ago while offline and delivered now: 30 minutes from THEN, not from now."""
    session, _ = pos_start(db, env)
    pressed = datetime.now(timezone.utc) - timedelta(hours=2)
    run(db, env, E(1, "time_extend", {"minutes": 30}, table_id=env.table.id, timestamp=pressed, clock_synced=True))
    assert as_utc(fresh(db, session).ends_at) == pressed + timedelta(minutes=30)


def test_time_extend_without_active_session_is_rejected(db, env):
    res = run(db, env, E(1, "time_extend", {"minutes": 30}, table_id=env.table.id))
    assert [r.event_id for r in res.rejected] == ["e1"] and "Session not found" in res.rejected[0].error
    assert event_row(db, "e1").status == DeviceEventStatus.REJECTED          # kept, the device keeps it
    assert res.server_state_version == 0


def test_time_extend_on_a_stopped_session_is_conflict(db, env):
    session, _ = pos_start(db, env)
    session_service.stop_session(db, session.id, env.user)
    db.commit()
    res = run(db, env, E(1, "time_extend", {"minutes": 30, "session_id": session.id}))
    assert [c.event_id for c in res.conflicts] == ["e1"]


@pytest.mark.parametrize("minutes", [0, -5, 481, "30", 30.5, True, None])
def test_time_extend_bad_minutes_are_rejected(db, env, minutes):
    pos_start(db, env)
    res = run(db, env, E(1, "time_extend", {"minutes": minutes}, table_id=env.table.id))
    assert [r.event_id for r in res.rejected] == ["e1"] and "minutes" in res.rejected[0].error


def test_time_extend_never_changes_package_items_billing_or_review(db, env):
    """Separation of concerns: a device event moves ends_at and nothing that was purchased or is owed."""
    beer = Product(name="Beer", base_price=20000, is_active=True)
    db.add(beer)
    db.flush()
    pkg = BilliardPackage(client_id="c1", name="1h", duration_minutes=60, price=Decimal("80000"), is_active=True)
    pkg.items = [BilliardPackageItem(product_id=beer.id, included_quantity=2)]
    db.add(pkg)
    db.commit()
    session = table_service.start_session(db, env.table.id, env.user, package_id=pkg.id)
    session_service.add_item(db, session.id, beer.id, 3, None, env.user)    # 2 free + 1 paid
    session_lifecycle.flag_billing_review(session, 424242, "Package not found")
    db.commit()
    snapshot = dict(session.package_snapshot)
    items = sorted((i.quantity, i.from_package, i.total_price) for i in session.items)
    money = (session.total_table_fee, session.total_product_fee, session.discount, session.grand_total)
    review = (session.billing_review_state, session.requested_package_id, session.billing_review_reason)

    res = run(db, env, E(1, "time_extend", {"minutes": 45}, table_id=env.table.id))
    assert res.accepted == ["e1"]
    s = fresh(db, session)
    assert s.package_snapshot == snapshot and s.package_name == "1h" and s.package_price == Decimal("80000.00")
    assert sorted((i.quantity, i.from_package, i.total_price) for i in s.items) == items
    assert (s.total_table_fee, s.total_product_fee, s.discount, s.grand_total) == money
    assert (s.billing_review_state, s.requested_package_id, s.billing_review_reason) == review
    # the free allowance is still used up: a third beer is charged
    extra = session_service.add_item(db, s.id, beer.id, 1, None, env.user)
    assert not extra.from_package


def test_time_extend_twice_adds_up(db, env):
    session, _ = pos_start(db, env)
    session.ends_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    db.commit()
    before = as_utc(session.ends_at)
    run(db, env, E(1, "time_extend", {"minutes": 10}, table_id=env.table.id),
        E(2, "time_extend", {"minutes": 20}, table_id=env.table.id))
    assert as_utc(fresh(db, session).ends_at) == before + timedelta(minutes=30)


# ---------------------------------------------------------------- table_status

@pytest.mark.parametrize("status, expected", [
    ("maintenance", TableStatus.MAINTENANCE), ("reserved", TableStatus.RESERVED)])
def test_table_status_event_sets_status(db, env, status, expected):
    res = run(db, env, E(1, "table_status", {"status": status, "expected_version": 0}, table_id=env.table.id))
    assert res.accepted == ["e1"]
    assert fresh(db, env.table).status == expected


def test_table_status_reserved_then_maintenance_then_available(db, env):
    res = run(db, env,
              E(1, "table_status", {"status": "reserved", "expected_version": 0}, table_id=env.table.id),
              E(2, "table_status", {"status": "maintenance", "expected_version": 1}, table_id=env.table.id),
              E(3, "table_status", {"status": "available", "expected_version": 2}, table_id=env.table.id))
    assert res.accepted == ["e1", "e2", "e3"] and res.server_state_version == 3
    assert fresh(db, env.table).status == TableStatus.AVAILABLE


def test_maintenance_event_blocks_a_new_session(db, env):
    run(db, env, E(1, "table_status", {"status": "maintenance", "expected_version": 0}, table_id=env.table.id))
    res = run(db, env, E(2, "session_start", table_id=env.table.id))
    assert [c.event_id for c in res.conflicts] == ["e2"] and "maintenance" in res.conflicts[0].error


def test_table_status_playing_event_is_rejected(db, env):
    res = run(db, env, E(1, "table_status", {"status": "playing", "expected_version": 0}, table_id=env.table.id))
    assert [r.event_id for r in res.rejected] == ["e1"] and "session_start" in res.rejected[0].error
    assert fresh(db, env.table).status == TableStatus.AVAILABLE


@pytest.mark.parametrize("status", ["broken", "", None, 5])
def test_table_status_unknown_value_is_rejected(db, env, status):
    res = run(db, env, E(1, "table_status", {"status": status, "expected_version": 0}, table_id=env.table.id))
    assert [r.event_id for r in res.rejected] == ["e1"]


@pytest.mark.parametrize("status", ["maintenance", "reserved", "available"])
def test_table_status_on_playing_table_is_conflict_and_not_applied(db, env, status):
    pos_start(db, env)
    version = fresh(db, env.table).status_version              # the device read the table AFTER the session started
    res = run(db, env, E(1, "table_status", {"status": status, "expected_version": version}, table_id=env.table.id))
    assert [c.event_id for c in res.conflicts] == ["e1"] and "active session" in res.conflicts[0].error
    assert fresh(db, env.table).status == TableStatus.PLAYING
    assert res.server_state_version == 0                      # a conflict is never acknowledged


def test_table_status_same_status_is_a_noop_that_is_accepted(db, env):
    run(db, env, E(1, "table_status", {"status": "maintenance", "expected_version": 0}, table_id=env.table.id))
    res = run(db, env, E(2, "table_status", {"status": "maintenance", "expected_version": 0}, table_id=env.table.id),
              E(3, "table_status", {"status": "available", "expected_version": 1}, table_id=env.table.id),
              E(4, "table_status", {"status": "available", "expected_version": 1}, table_id=env.table.id))
    assert res.accepted == ["e2", "e3", "e4"] and res.server_state_version == 4
    assert event_row(db, "e2").payload["reconciled"] == {"already": "maintenance", "status_version": 1}


def test_table_status_reserved_on_maintenance_table_is_conflict(db, env):
    run(db, env, E(1, "table_status", {"status": "maintenance", "expected_version": 0}, table_id=env.table.id))
    res = run(db, env, E(2, "table_status", {"status": "reserved", "expected_version": 1}, table_id=env.table.id))
    assert [c.event_id for c in res.conflicts] == ["e2"]


def test_table_status_without_table_is_rejected(db, env):
    res = run(db, env, E(1, "table_status", {"status": "maintenance", "expected_version": 0}))
    assert [r.event_id for r in res.rejected] == ["e1"] and "table_id" in res.rejected[0].error


# ---------------------------------------------------------------- button_press

def _game(db, env):
    session, game = pos_start(db, env, with_game=True)
    return session, game


def test_button_press_score_up_runs_the_score_handler(db, env):
    _, game = _game(db, env)
    res = run(db, env,
              E(1, "button_press", {"action": "score_a_up"}, table_id=env.table.id),
              E(2, "button_press", {"action": "score_a_up"}, table_id=env.table.id),
              E(3, "button_press", {"action": "score_b_up"}, table_id=env.table.id))
    assert res.accepted == ["e1", "e2", "e3"]
    g = fresh(db, game)
    assert (g.player_a_score, g.player_b_score) == (2, 1)
    assert event_row(db, "e3").payload["reconciled"] == {"button": "score_b_up", "score": [2, 1]}


def test_button_press_score_down_never_goes_below_zero(db, env):
    _, game = _game(db, env)
    run(db, env, E(1, "button_press", {"action": "score_a_down"}, table_id=env.table.id))
    assert fresh(db, game).player_a_score == 0


def test_button_press_reset_score(db, env):
    _, game = _game(db, env)
    run(db, env, E(1, "button_press", {"action": "score_a_up"}, table_id=env.table.id),
        E(2, "button_press", {"action": "reset_score"}, table_id=env.table.id))
    g = fresh(db, game)
    assert (g.player_a_score, g.player_b_score) == (0, 0)


def test_button_press_new_game_closes_the_game_and_opens_the_next(db, env):
    session, game = _game(db, env)
    res = run(db, env, E(1, "button_press", {"action": "new_game", "new_local_game_id": "LOCAL-G-2"},
                         table_id=env.table.id))
    assert res.accepted == ["e1"]
    games = db.execute(select(type(game)).where(type(game).session_id == session.id)).scalars().all()
    assert len(games) == 2 and sum(1 for g in games if g.status.value == "active") == 1


def test_button_press_end_game(db, env):
    _, game = _game(db, env)
    run(db, env, E(1, "button_press", {"action": "end_game"}, table_id=env.table.id))
    assert fresh(db, game).status.value == "completed"


@pytest.mark.parametrize("action", ["selfdestruct", "", None, 7])
def test_button_press_unknown_action_is_rejected_with_a_message(db, env, action):
    _game(db, env)
    res = run(db, env, E(1, "button_press", {"action": action}, table_id=env.table.id))
    assert [r.event_id for r in res.rejected] == ["e1"] and "Unknown button action" in res.rejected[0].error
    assert event_row(db, "e1").status == DeviceEventStatus.REJECTED          # not silently dropped


def test_button_press_without_a_game_is_rejected(db, env):
    pos_start(db, env)
    res = run(db, env, E(1, "button_press", {"action": "score_a_up"}, table_id=env.table.id))
    assert [r.event_id for r in res.rejected] == ["e1"] and "Game not found" in res.rejected[0].error


def test_button_actions_are_defined_in_one_place():
    assert set(BUTTON_ACTIONS) == {
        "score_a_up", "score_a_down", "score_b_up", "score_b_down", "reset_score", "new_game", "end_game"}


# ---------------------------------------------------------------- device_error

def test_device_error_is_processed_and_recorded(db, env):
    res = run(db, env, E(1, "device_error", {"code": "RS485_TIMEOUT", "message": "No reply from table 3"}))
    assert res.accepted == ["e1"] and res.server_state_version == 1
    d = fresh(db, env.device)
    assert d.last_error == "RS485_TIMEOUT: No reply from table 3" and d.last_error_at is not None
    row = event_row(db, "e1")
    assert row.status == DeviceEventStatus.PROCESSED
    assert row.payload["reconciled"] == {"code": "RS485_TIMEOUT", "message": "No reply from table 3"}


def test_device_error_latest_wins_and_code_only_is_fine(db, env):
    run(db, env, E(1, "device_error", {"code": "A", "message": "first"}), E(2, "device_error", {"code": "B"}))
    assert fresh(db, env.device).last_error == "B"


def test_device_error_without_data_is_still_accepted(db, env):
    res = run(db, env, E(1, "device_error"))
    assert res.accepted == ["e1"] and fresh(db, env.device).last_error == "unspecified"


def test_device_error_long_text_is_truncated(db, env):
    run(db, env, E(1, "device_error", {"code": "X" * 500, "message": "m" * 500}))
    assert len(fresh(db, env.device).last_error) <= 255
    assert len(event_row(db, "e1").payload["reconciled"]["code"]) == 64


def test_device_error_does_not_touch_sessions_or_tables(db, env):
    session, _ = pos_start(db, env)
    run(db, env, E(1, "device_error", {"code": "OVERHEAT"}, table_id=env.table.id))
    assert fresh(db, session).status == SessionStatus.ACTIVE and fresh(db, env.table).status == TableStatus.PLAYING


def test_device_error_is_shown_in_controller_status(db, env):
    run(db, env, E(1, "device_error", {"code": "RS485_TIMEOUT", "message": "no reply"}))
    app = FastAPI()
    app.include_router(controller_router)
    manager = User(client_id="c1", username="boss", email="b@x.com", hashed_password="x")
    db.add(manager)
    db.commit()
    from app.user.utils.token import get_current_user
    from types import SimpleNamespace
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=manager.id, client_id="c1", username="boss", is_super_admin=lambda: False, has_role=lambda r: True)
    resp = TestClient(app).get("/billiard/controller/status")
    assert resp.status_code == 200
    rows = resp.json()
    assert rows[0]["last_error"] == "RS485_TIMEOUT: no reply" and rows[0]["last_error_at"] is not None


# ---------------------------------------------------------------- cross-cutting

NEW_EVENTS = [
    ("time_extend", {"minutes": 10}), ("table_status", {"status": "maintenance", "expected_version": 0}),
    ("button_press", {"action": "score_a_up"}), ("device_error", {"code": "E1"}),
]


@pytest.mark.parametrize("kind, data", NEW_EVENTS)
def test_new_events_are_idempotent(db, env, kind, data):
    pos_start(db, env, with_game=True) if kind != "table_status" else None
    ev = E(1, kind, data, table_id=env.table.id)
    first = run(db, env, ev)
    again = run(db, env, ev)
    assert first.accepted == ["e1"] and again.duplicates == ["e1"] and again.accepted == []
    assert db.execute(select(DeviceEvent).where(DeviceEvent.event_id == "e1")).scalars().all().__len__() == 1


def test_a_duplicate_time_extend_extends_only_once(db, env):
    session, _ = pos_start(db, env)
    session.ends_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    db.commit()
    before = as_utc(session.ends_at)
    ev = E(1, "time_extend", {"minutes": 30}, table_id=env.table.id)
    run(db, env, ev)
    run(db, env, ev)
    assert as_utc(fresh(db, session).ends_at) == before + timedelta(minutes=30)


def test_new_events_respect_device_seq_order_and_cursor(db, env):
    pos_start(db, env, with_game=True)
    # batch 1 arrives with a gap (seq 1 missing): processed, but the cursor does not move
    res = run(db, env, E(2, "button_press", {"action": "score_a_up"}, table_id=env.table.id),
              E(3, "device_error", {"code": "X"}))
    assert res.accepted == ["e2", "e3"] and res.server_state_version == 0
    res = run(db, env, E(1, "time_extend", {"minutes": 5}, table_id=env.table.id))
    assert res.accepted == ["e1"] and res.server_state_version == 3       # the gap is filled: advances over all three


def test_events_in_one_batch_are_applied_by_seq_not_by_list_order(db, env):
    pos_start(db, env, with_game=True)
    res = run(db, env,
              E(2, "button_press", {"action": "score_a_down"}, table_id=env.table.id),     # 1 -> 0
              E(1, "button_press", {"action": "score_a_up"}, table_id=env.table.id))       # 0 -> 1
    assert res.accepted == ["e1", "e2"]
    from app.billiard.models import TableGame
    assert db.execute(select(TableGame.player_a_score)).scalar_one() == 0      # up first (1), then down (0)


def test_a_rejected_new_event_blocks_the_cursor_until_resolved(db, env):
    res = run(db, env, E(1, "table_status", {"status": "playing"}, table_id=env.table.id),
              E(2, "device_error", {"code": "X"}))
    assert [r.event_id for r in res.rejected] == ["e1"] and res.accepted == ["e2"]
    assert res.server_state_version == 0


@pytest.mark.parametrize("kind, data", NEW_EVENTS[:3])
def test_new_events_cannot_cross_tenant(db, env, kind, data):
    other_table = BilliardTable(name="Other", client_id="c2", hourly_rate=Decimal("100000"))
    db.add(other_table)
    db.commit()
    res = run(db, env, E(1, kind, data, table_id=other_table.id))
    assert [r.event_id for r in res.rejected] == ["e1"]
    assert fresh(db, other_table).status == TableStatus.AVAILABLE


def test_a_session_of_another_club_cannot_be_extended_by_id(db, env):
    other = BilliardTable(name="Other", client_id="c2", hourly_rate=Decimal("100000"))
    db.add(other)
    db.flush()
    foreign = session_lifecycle.open_session(db, other, None)
    db.commit()
    res = run(db, env, E(1, "time_extend", {"minutes": 10, "session_id": foreign.id}))
    assert [r.event_id for r in res.rejected] == ["e1"] and foreign.ends_at is None


@pytest.mark.parametrize("kind, data", NEW_EVENTS[:3])
def test_device_clock_rules_apply_to_new_events(db, env, kind, data):
    pos_start(db, env, with_game=True)
    future = datetime.now(timezone.utc) + timedelta(hours=3)
    old = datetime.now(timezone.utc) - timedelta(hours=60)
    r1 = run(db, env, E(1, kind, data, table_id=env.table.id, timestamp=future, clock_synced=True))
    r2 = run(db, env, E(2, kind, data, table_id=env.table.id, timestamp=old, clock_synced=True))
    assert [r.event_id for r in r1.rejected] == ["e1"] and "ahead of server time" in r1.rejected[0].error
    assert [r.event_id for r in r2.rejected] == ["e2"] and "too old" in r2.rejected[0].error


def test_unsynced_clock_is_ignored_not_rejected(db, env):
    pos_start(db, env)
    res = run(db, env, E(1, "time_extend", {"minutes": 10}, table_id=env.table.id,
                         timestamp=datetime.now(timezone.utc) + timedelta(hours=9), clock_synced=False))
    assert res.accepted == ["e1"]


def test_every_event_type_now_has_a_handler():
    from app.billiard.models import DeviceEventType
    from app.billiard.services.event_service import HANDLERS
    assert set(HANDLERS) == set(DeviceEventType)


def test_pos_table_status_still_works_after_sharing_the_active_session_guard(db, env):
    session, _ = pos_start(db, env)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        table_service.set_status(db, env.table.id, "maintenance", env.user)
    assert e.value.status_code == 409 and "stop its session first" in e.value.detail


# ---------------------------------------------------------------- stale status protection (status_version)

def ts(seq, status, version, **kw):
    return E(seq, "table_status", {"status": status, "expected_version": version}, **kw)


def version_of(db, table):
    return fresh(db, table).status_version


def test_status_version_counts_every_real_change(db, env):
    assert version_of(db, env.table) == 0
    table_service.set_status(db, env.table.id, "reserve", env.user)
    table_service.set_status(db, env.table.id, "maintenance", env.user)
    table_service.set_status(db, env.table.id, "release", env.user)
    db.commit()
    assert version_of(db, env.table) == 3
    session = table_service.start_session(db, env.table.id, env.user)       # available -> playing
    db.commit()
    assert version_of(db, env.table) == 4
    session_service.stop_session(db, session.id, env.user)                  # playing -> available
    db.commit()
    assert version_of(db, env.table) == 5


def test_failed_or_identical_changes_do_not_bump_the_version(db, env):
    from fastapi import HTTPException
    table_service.set_status(db, env.table.id, "maintenance", env.user)
    db.commit()
    with pytest.raises(HTTPException):
        table_service.set_status(db, env.table.id, "reserve", env.user)     # refused: maintenance
    with pytest.raises(HTTPException):
        table_service.set_status(db, env.table.id, "maintenance", env.user)  # refused: same status
    db.commit()
    assert version_of(db, env.table) == 1


def test_controller_state_exposes_the_status_version(db, env):
    from app.billiard.services.device_service import device_service
    table_service.set_status(db, env.table.id, "reserve", env.user)
    db.commit()
    state = device_service.build_state(db, env.device)
    assert [(t.table_id, t.status.value, t.status_version) for t in state.tables] == [(env.table.id, "reserved", 1)]


def test_delayed_device_event_cannot_overwrite_a_newer_pos_change(db, env):
    """The device read version 0, went offline, and queued 'maintenance'. Meanwhile the POS reserved the table."""
    seen = version_of(db, env.table)                                         # 0: what the device saw
    table_service.set_status(db, env.table.id, "reserve", env.user)          # newer POS change
    db.commit()

    res = run(db, env, ts(1, "maintenance", seen, table_id=env.table.id))

    assert res.accepted == [] and [c.event_id for c in res.conflicts] == ["e1"]
    assert "Stale table_status" in res.conflicts[0].error
    assert fresh(db, env.table).status == TableStatus.RESERVED               # the POS change survived
    assert version_of(db, env.table) == 1                                    # and nothing was bumped
    row = event_row(db, "e1")                                                # logged, not lost
    assert row.status == DeviceEventStatus.CONFLICT
    assert "version 0" in row.error and "version 1" in row.error and "reserved" in row.error
    assert row.payload["status"] == "maintenance" and row.payload["expected_version"] == 0
    assert res.server_state_version == 0                                     # the device still holds this event


def test_delayed_status_event_after_a_session_started_and_stopped_is_stale(db, env):
    seen = version_of(db, env.table)
    session, _ = pos_start(db, env)
    session_service.stop_session(db, session.id, env.user)
    db.commit()                                                              # available again, but version 2
    res = run(db, env, ts(1, "maintenance", seen, table_id=env.table.id))
    assert [c.event_id for c in res.conflicts] == ["e1"] and fresh(db, env.table).status == TableStatus.AVAILABLE


def test_device_can_apply_the_change_after_reading_the_new_version(db, env):
    table_service.set_status(db, env.table.id, "reserve", env.user)
    db.commit()
    res = run(db, env, ts(1, "maintenance", 0, table_id=env.table.id),       # stale: refused
              ts(2, "maintenance", 1, table_id=env.table.id))                # re-decided on version 1: applied
    assert [c.event_id for c in res.conflicts] == ["e1"] and res.accepted == ["e2"]
    assert fresh(db, env.table).status == TableStatus.MAINTENANCE and version_of(db, env.table) == 2
    assert event_row(db, "e2").payload["reconciled"] == {"previous": "reserved", "status_version": 2}
    # Known rule (unchanged): a conflict is never acknowledged, so the cursor stays below it.
    assert res.server_state_version == 0


def test_a_stale_event_does_not_touch_anything_else(db, env):
    session, _ = pos_start(db, env)
    ends = session.ends_at
    res = run(db, env, ts(1, "maintenance", 0, table_id=env.table.id))
    assert [c.event_id for c in res.conflicts] == ["e1"]
    s = fresh(db, session)
    assert s.status == SessionStatus.ACTIVE and s.ends_at == ends and fresh(db, env.table).status == TableStatus.PLAYING


def test_repeated_identical_status_events_are_idempotent_and_keep_the_cursor_moving(db, env):
    first = run(db, env, ts(1, "maintenance", 0, table_id=env.table.id))
    assert first.accepted == ["e1"] and first.server_state_version == 1
    # same intent again, under new event ids and the now-stale version 0: harmless no-ops
    again = run(db, env, ts(2, "maintenance", 0, table_id=env.table.id), ts(3, "maintenance", 0, table_id=env.table.id))
    assert again.accepted == ["e2", "e3"] and again.conflicts == [] and again.server_state_version == 3
    assert version_of(db, env.table) == 1                                    # no extra bumps
    assert event_row(db, "e2").payload["reconciled"] == {"already": "maintenance", "status_version": 1}


def test_a_pos_change_to_the_same_status_makes_the_late_device_event_a_noop(db, env):
    table_service.set_status(db, env.table.id, "maintenance", env.user)      # POS got there first
    db.commit()
    res = run(db, env, ts(1, "maintenance", 0, table_id=env.table.id))
    assert res.accepted == ["e1"] and res.server_state_version == 1 and version_of(db, env.table) == 1


def test_duplicate_status_event_is_acknowledged_without_reapplying(db, env):
    ev = ts(1, "maintenance", 0, table_id=env.table.id)
    assert run(db, env, ev).accepted == ["e1"]
    table_service.set_status(db, env.table.id, "release", env.user)          # POS moves on
    db.commit()
    again = run(db, env, ev)                                                 # the device resends the SAME event
    assert again.duplicates == ["e1"] and again.accepted == [] and again.conflicts == []
    assert fresh(db, env.table).status == TableStatus.AVAILABLE              # the duplicate did not re-apply


def test_out_of_order_status_events_are_not_applied_ahead_of_their_predecessor(db, env):
    # seq 1: reserved (version 0 -> 1). seq 2 was decided on that result (version 1): maintenance. seq 2 arrives first.
    early = run(db, env, ts(2, "maintenance", 1, table_id=env.table.id))
    assert [c.event_id for c in early.conflicts] == ["e2"] and early.server_state_version == 0
    assert fresh(db, env.table).status == TableStatus.AVAILABLE and version_of(db, env.table) == 0
    first = run(db, env, ts(1, "reserved", 0, table_id=env.table.id))        # seq 1 now applies normally
    assert first.accepted == ["e1"] and fresh(db, env.table).status == TableStatus.RESERVED
    assert version_of(db, env.table) == 1


def test_status_events_in_one_batch_apply_in_seq_order(db, env):
    res = run(db, env,                                                       # listed backwards on purpose
              ts(2, "available", 1, table_id=env.table.id),
              ts(1, "maintenance", 0, table_id=env.table.id))
    assert res.accepted == ["e1", "e2"] and res.server_state_version == 2
    assert fresh(db, env.table).status == TableStatus.AVAILABLE and version_of(db, env.table) == 2


@pytest.mark.parametrize("data", [
    {"status": "maintenance"},                                   # missing
    {"status": "maintenance", "expected_version": "0"},          # not a number
    {"status": "maintenance", "expected_version": -1},
    {"status": "maintenance", "expected_version": 1.5},
    {"status": "maintenance", "expected_version": True},
    {"status": "maintenance", "expected_version": None},
])
def test_table_status_without_a_valid_expected_version_is_rejected(db, env, data):
    res = run(db, env, E(1, "table_status", data, table_id=env.table.id))
    assert [r.event_id for r in res.rejected] == ["e1"] and "expected_version" in res.rejected[0].error
    assert fresh(db, env.table).status == TableStatus.AVAILABLE


def test_time_extend_is_unaffected_by_status_versioning(db, env):
    session, _ = pos_start(db, env)
    version = version_of(db, env.table)
    session.ends_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    db.commit()
    before = as_utc(session.ends_at)
    res = run(db, env, E(1, "time_extend", {"minutes": 20}, table_id=env.table.id))      # no expected_version needed
    assert res.accepted == ["e1"] and as_utc(fresh(db, session).ends_at) == before + timedelta(minutes=20)
    assert version_of(db, env.table) == version                                          # it never changes the status
