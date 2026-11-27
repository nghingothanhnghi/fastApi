# app/tests/test_billiard_realtime.py
# Roadmap item I: WS /ws/billiard pushes id-only updates after commit. Polling stays the fallback.
import asyncio
import importlib
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from app.billiard import config
from app.billiard.models import (
    BilliardDevice, BilliardTable, DeviceStatus, TableSession, TableStatus,
)
from app.billiard.routes.controller_router import router as controller_router
from app.billiard.routes.session_router import router as session_router
from app.billiard.routes.table_router import router as table_router
from app.billiard.routes.ws_router import router as ws_router
from app.billiard.services import device_watchdog, game_lifecycle, realtime, session_lifecycle
from app.billiard.services.device_auth import hash_api_key
from app.billiard.services.event_service import event_service
from app.billiard.services.realtime import InProcessRealtime, set_realtime
from app.billiard.utils.billing import as_utc
from app.database import Base, get_db
from app.product.models.product import Product
from app.tests._billiard_fixtures import make_table, make_user
from app.tests.test_billing_review import grant
from jose import jwt
from app.user.utils.token import ALGORITHM, SECRET_KEY, get_current_user

ws_module = importlib.import_module("app.billiard.routes.ws_router")      # the module (routes/__init__ re-exports the router under this name)
ALLOWED_KEYS = {"type", "table_id", "session_id", "game_id", "device_id", "status", "version"}


def E(seq, kind, data=None, **kw):
    from app.billiard.schemas.event import DeviceEventIn as Ev
    return Ev(event_id=f"rt-{seq}", event=kind, device_seq=seq, data=data or {}, **kw)


@pytest.fixture()
def rt():
    fresh = InProcessRealtime()
    previous = set_realtime(fresh)
    yield fresh
    set_realtime(previous)


@pytest.fixture()
def world(rt, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine)
    seed = Session_()
    staff = make_user(seed, "c1", "staff1")
    staff2 = make_user(seed, "c1", "staff2")
    other = make_user(seed, "c2", "staff3")
    inactive = make_user(seed, "c1", "gone")
    inactive.is_active = False
    boss = grant(seed, make_user(seed, "c3", "boss"), "super_admin")
    table = make_table(seed, "c1", "T1")
    table_c2 = make_table(seed, "c2", "T9")
    beer = Product(name="Beer", base_price=20000, is_active=True)
    seed.add(beer)
    device = BilliardDevice(client_id="c1", device_id="DEV1", name="ctrl", api_key_hash=hash_api_key("secret"),
                           status=DeviceStatus.ONLINE, last_seen=datetime.now(timezone.utc))
    seed.add(device)
    seed.commit()
    ids = SimpleNamespace(
        staff=staff.id, table=table.id, table_c2=table_c2.id, beer=beer.id, device=device.id,
        token=lambda name: jwt.encode(
            {"sub": name, "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, SECRET_KEY, algorithm=ALGORITHM),
    )
    seed.close()

    monkeypatch.setattr(ws_module, "SessionLocal", Session_)          # the socket looks users up here
    app = FastAPI()
    for r in (table_router, session_router, controller_router, ws_router):
        app.include_router(r)

    def _db():
        s = Session_()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=ids.staff, client_id="c1", username="staff1", is_super_admin=lambda: False, has_role=lambda r: True)
    client = TestClient(app)
    client.ids, client.Session, client.rt = ids, Session_, rt
    return client


def drain(ws, rt, club):
    """Everything queued before now. A sentinel goes through the same pipe, so ordering proves 'nothing else came'."""
    rt.publish(club, {"type": "sentinel"})
    out = []
    while True:
        msg = ws.receive_json()
        if msg["type"] == "sentinel":
            return out
        out.append(msg)


def open_ws(client, name="staff1", **params):
    query = "&".join(f"{k}={v}" for k, v in {"token": client.ids.token(name), **params}.items())
    return client.websocket_connect(f"/ws/billiard?{query}")


def by_type(messages, kind):
    return [m for m in messages if m["type"] == kind]


# ---------------------------------------------------------------- connection and authentication

@pytest.mark.parametrize("query", ["", "token=not-a-jwt"])
def test_ws_rejects_missing_or_bad_token(world, query):
    with world.websocket_connect(f"/ws/billiard?{query}") as ws:
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == 1008


def test_ws_rejects_unknown_and_inactive_users(world):
    for name in ("nobody", "gone"):
        with open_ws(world, name) as ws:
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
        assert closed.value.code == 1008


def test_ws_says_ready_and_joins_the_users_club(world):
    with open_ws(world) as ws:
        ready = ws.receive_json()
        assert ready == {"type": "ready", "client_id": "c1", "ping_seconds": config.WS_PING_SECONDS}
        assert world.rt.room_size("c1") == 1
    for _ in range(50):                                                  # the room is left on disconnect
        if world.rt.room_size("c1") == 0:
            break
        asyncio.run(asyncio.sleep(0.02))
    assert world.rt.room_size("c1") == 0 and not world.rt.active


def test_a_user_cannot_listen_to_another_club(world):
    with open_ws(world, "staff1", client_id="c2") as ws:
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == 1008
    with open_ws(world, "staff1", client_id="c1") as ws:                 # asking for its own club is fine
        assert ws.receive_json()["client_id"] == "c1"


def test_super_admin_room_selection(world):
    with open_ws(world, "boss", client_id="c2") as ws:                   # chosen club
        assert ws.receive_json()["client_id"] == "c2"
    with open_ws(world, "boss") as ws:                                   # no choice: its own club
        assert ws.receive_json()["client_id"] == "c3"


def test_server_pings(world, monkeypatch):
    monkeypatch.setattr(config, "WS_PING_SECONDS", 0.05)
    with open_ws(world) as ws:
        assert ws.receive_json()["type"] == "ready"
        assert ws.receive_json() == {"type": "ping"}
        ws.send_text("pong")                                             # client chatter is ignored
        assert ws.receive_json() == {"type": "ping"}


# ---------------------------------------------------------------- messages after a POS change

def test_ws_receives_table_changed_after_start(world):
    i = world.ids
    with open_ws(world) as ws:
        ws.receive_json()
        sid = world.post(f"/tables/{i.table}/start", json={}).json()["session_id"]
        got = drain(ws, world.rt, "c1")
    assert by_type(got, "table.changed") == [{"type": "table.changed", "table_id": i.table, "version": 1}]
    assert by_type(got, "session.changed") == [{"type": "session.changed", "session_id": sid, "table_id": i.table}]
    assert len(got) == 2


def test_stop_items_and_extend_notify_their_session(world):
    i = world.ids
    with open_ws(world) as ws:
        ws.receive_json()
        sid = world.post(f"/tables/{i.table}/start", json={"planned_minutes": 30}).json()["session_id"]
        drain(ws, world.rt, "c1")
        world.post(f"/sessions/{sid}/items", json={"product_id": i.beer, "quantity": 2})
        items = drain(ws, world.rt, "c1")
        world.post(f"/sessions/{sid}/extend", json={"minutes": 15})
        extend = drain(ws, world.rt, "c1")
        world.post(f"/sessions/{sid}/stop")
        stop = drain(ws, world.rt, "c1")
    assert items == [{"type": "session.changed", "session_id": sid, "table_id": i.table}]
    assert extend == [{"type": "session.changed", "session_id": sid, "table_id": i.table}]
    assert {m["type"] for m in stop} == {"table.changed", "session.changed"}
    assert by_type(stop, "table.changed")[0]["version"] == 2            # playing -> available


def test_one_message_per_thing_however_many_changes(world):
    """Two items and a discount in one transaction are still one session.changed."""
    i = world.ids
    with open_ws(world) as ws:
        ws.receive_json()
        sid = world.post(f"/tables/{i.table}/start", json={}).json()["session_id"]
        drain(ws, world.rt, "c1")
        db = world.Session()
        s = db.get(TableSession, sid)
        from app.billiard.services.session_service import session_service
        user = SimpleNamespace(id=i.staff, client_id="c1", is_super_admin=lambda: False, has_role=lambda r: True)
        session_service.add_item(db, sid, i.beer, 1, None, user)
        session_service.add_item(db, sid, i.beer, 2, None, user)
        session_lifecycle.apply_discount(s, percent=10)
        db.commit()
        db.close()
        got = drain(ws, world.rt, "c1")
    assert got == [{"type": "session.changed", "session_id": sid, "table_id": i.table}]


def test_ws_not_notified_when_transaction_rolls_back(world):
    i = world.ids
    with open_ws(world) as ws:
        ws.receive_json()
        db = world.Session()
        table = db.get(BilliardTable, i.table)
        session_lifecycle.open_session(db, table, i.staff)
        db.flush()                                                        # the change exists inside the transaction
        assert drain(ws, world.rt, "c1") == []                            # ... but nothing is sent before commit
        db.rollback()
        db.commit()                                                       # the same session goes on (as the controller path does)
        db.close()
        assert drain(ws, world.rt, "c1") == []                            # and nothing after a rollback
        db2 = world.Session()
        session_lifecycle.open_session(db2, db2.get(BilliardTable, i.table), i.staff)
        db2.commit()
        db2.close()
        assert {m["type"] for m in drain(ws, world.rt, "c1")} == {"table.changed", "session.changed"}


def test_a_row_of_the_bill_alone_is_enough_to_notify_its_session(world):
    """Only an item row changes (the session row itself is untouched): the POS must still refresh that bill."""
    i = world.ids
    sid = world.post(f"/tables/{i.table}/start", json={}).json()["session_id"]
    from app.billiard.models import SessionItem
    with open_ws(world) as ws:
        ws.receive_json()
        db = world.Session()
        db.add(SessionItem(session_id=sid, product_id=i.beer, product_name="Beer", quantity=1,
                           unit_price=20000, total_price=20000))
        db.commit()
        db.close()
        assert drain(ws, world.rt, "c1") == [{"type": "session.changed", "session_id": sid, "table_id": i.table}]


def test_a_failed_request_sends_nothing(world):
    """A start that the server refuses (table in maintenance) changes nothing and tells nobody."""
    i = world.ids
    db = world.Session()
    db.get(BilliardTable, i.table).status = TableStatus.MAINTENANCE
    db.commit()
    db.close()
    with open_ws(world) as ws:
        ws.receive_json()
        assert world.post(f"/tables/{i.table}/start", json={}).status_code >= 400
        assert drain(ws, world.rt, "c1") == []


def test_ws_message_is_not_sent_to_other_tenant(world):
    i = world.ids
    with open_ws(world, "staff1") as mine, open_ws(world, "staff3") as theirs:
        mine.receive_json(), theirs.receive_json()
        world.post(f"/tables/{i.table}/start", json={})
        assert len(drain(mine, world.rt, "c1")) == 2
        assert drain(theirs, world.rt, "c2") == []                        # c2 never hears about c1


def test_a_change_in_the_other_club_is_not_heard_here(world):
    i = world.ids
    with open_ws(world, "staff1") as mine:
        mine.receive_json()
        db = world.Session()
        session_lifecycle.open_session(db, db.get(BilliardTable, i.table_c2), None)
        db.commit()
        db.close()
        assert drain(mine, world.rt, "c1") == []


def test_multiple_clients_same_tenant_all_receive(world):
    i = world.ids
    with open_ws(world, "staff1") as a, open_ws(world, "staff2") as b:
        a.receive_json(), b.receive_json()
        assert world.rt.room_size("c1") == 2
        world.post(f"/tables/{i.table}/start", json={})
        got_a, got_b = drain(a, world.rt, "c1"), drain(b, world.rt, "c1")
    assert got_a == got_b and len(got_a) == 2


def test_messages_contain_ids_only_no_money_fields(world):
    i = world.ids
    seen = []
    with open_ws(world) as ws:
        ws.receive_json()
        sid = world.post(f"/tables/{i.table}/start", json={}).json()["session_id"]
        seen += drain(ws, world.rt, "c1")
        world.post(f"/sessions/{sid}/items", json={"product_id": i.beer, "quantity": 3})
        seen += drain(ws, world.rt, "c1")
        world.post(f"/sessions/{sid}/stop")
        seen += drain(ws, world.rt, "c1")
    assert seen
    for message in seen:
        assert set(message) <= ALLOWED_KEYS, message
        assert not any(w in json.dumps(message).lower() for w in ("fee", "price", "total", "amount", "discount", "name"))


# ---------------------------------------------------------------- messages from the controller

def controller_session(world):
    db = world.Session()
    table = db.get(BilliardTable, world.ids.table)
    s = session_lifecycle.open_session(db, table, world.ids.staff)
    g = game_lifecycle.open_game(db, s)
    db.commit()
    out = (s.id, g.id)
    db.close()
    return out


def device_post(world, *events):
    body = {"device_id": "DEV1", "events": [json.loads(e.model_dump_json()) for e in events]}
    return world.post("/billiard/controller/sync", json=body, headers={"X-Device-Id": "DEV1", "X-Device-Key": "secret"})


def test_controller_event_notifies_pos(world):
    sid, gid = controller_session(world)
    with open_ws(world) as ws:
        ws.receive_json()
        r = device_post(world, E(1, "score_change", {"game_id": gid, "score_a": 5, "score_b": 3}))
        assert r.status_code == 200 and r.json()["accepted"] == ["rt-1"], r.text
        got = drain(ws, world.rt, "c1")
    assert got == [{"type": "game.changed", "game_id": gid, "session_id": sid}]


def test_controller_time_extend_and_table_status_use_the_same_messages(world):
    sid, gid = controller_session(world)
    i = world.ids
    with open_ws(world) as ws:
        ws.receive_json()
        device_post(world, E(1, "time_extend", {"minutes": 10}, table_id=i.table))
        extend = drain(ws, world.rt, "c1")
        # close the session so the table can be reserved by the device
        db = world.Session()
        s = db.get(TableSession, sid)
        session_lifecycle.finalize_stop(db, s, db.get(BilliardTable, i.table), None)
        db.commit()
        version = db.get(BilliardTable, i.table).status_version
        db.close()
        drain(ws, world.rt, "c1")
        device_post(world, E(2, "table_status", {"status": "reserved", "expected_version": version}, table_id=i.table))
        status = drain(ws, world.rt, "c1")
    assert extend == [{"type": "session.changed", "session_id": sid, "table_id": i.table}]
    assert status == [{"type": "table.changed", "table_id": i.table, "version": version + 1}]


def test_a_stale_device_event_sends_nothing_about_the_table(world):
    """A conflict changes no table, so the POS is not told the table changed."""
    i = world.ids
    with open_ws(world) as ws:
        ws.receive_json()
        device_post(world, E(1, "table_status", {"status": "maintenance", "expected_version": 99}, table_id=i.table))
        got = drain(ws, world.rt, "c1")
    assert by_type(got, "table.changed") == []


def test_heartbeat_alone_does_not_spam_the_pos(world):
    with open_ws(world) as ws:
        ws.receive_json()
        device_post(world, E(1, "heartbeat", {"firmware_version": "1.0"}))
        assert drain(ws, world.rt, "c1") == []


# ---------------------------------------------------------------- device status (item H)

def test_device_offline_notifies_pos(world):
    db = world.Session()
    device = db.get(BilliardDevice, world.ids.device)
    device.status, device.last_seen = DeviceStatus.ONLINE, datetime.now(timezone.utc) - timedelta(seconds=500)
    db.commit()
    with open_ws(world) as ws:
        ws.receive_json()
        device_watchdog.sweep_offline(db)
        assert drain(ws, world.rt, "c1") == []                            # not before the commit
        db.commit()
        got = drain(ws, world.rt, "c1")
        db.close()
    assert got == [{"type": "device.status", "device_id": "DEV1", "status": "offline"}]


def test_device_back_online_notifies_pos_once(world):
    db = world.Session()
    db.get(BilliardDevice, world.ids.device).status = DeviceStatus.OFFLINE
    db.commit()
    db.close()
    with open_ws(world) as ws:
        ws.receive_json()
        device_post(world, E(1, "heartbeat"))
        device_post(world, E(2, "heartbeat"))                             # already online: no second message
        got = drain(ws, world.rt, "c1")
    assert got == [{"type": "device.status", "device_id": "DEV1", "status": "online"}]


def test_a_rolled_back_sweep_does_not_announce_offline(world):
    db = world.Session()
    device = db.get(BilliardDevice, world.ids.device)
    device.status, device.last_seen = DeviceStatus.ONLINE, datetime.now(timezone.utc) - timedelta(seconds=500)
    db.commit()
    with open_ws(world) as ws:
        ws.receive_json()
        device_watchdog.sweep_offline(db)
        db.rollback()
        db.close()
        assert drain(ws, world.rt, "c1") == []


# ---------------------------------------------------------------- the manager itself

class FakeSocket:
    def __init__(self, behaviour="ok"):
        self.behaviour, self.sent, self.closed = behaviour, [], False

    async def send_json(self, message):
        if self.behaviour == "dead":
            raise RuntimeError("connection reset")
        if self.behaviour == "slow":
            await asyncio.sleep(5)
        self.sent.append(message)

    async def close(self):
        self.closed = True


def test_dead_socket_is_removed_and_others_still_receive(monkeypatch):
    monkeypatch.setattr(config, "WS_SEND_TIMEOUT_SECONDS", 0.1)

    async def scenario():
        manager = InProcessRealtime()
        good, dead, slow = FakeSocket(), FakeSocket("dead"), FakeSocket("slow")
        for s in (good, dead, slow):
            await manager.connect("c1", s)
        manager.publish("c1", {"type": "table.changed", "table_id": 1, "version": 1})
        await asyncio.sleep(0.4)
        assert good.sent == [{"type": "table.changed", "table_id": 1, "version": 1}]
        assert manager.room_size("c1") == 1 and dead.closed and slow.closed      # the failing ones are gone
        manager.publish("c1", {"type": "table.changed", "table_id": 1, "version": 2})
        await asyncio.sleep(0.1)
        assert [m["version"] for m in good.sent] == [1, 2]

    asyncio.run(scenario())


def test_publish_with_nobody_listening_is_a_cheap_no_op(rt):
    rt.publish("c9", {"type": "table.changed", "table_id": 1, "version": 1})
    assert not rt.active


def test_nothing_is_queued_while_nobody_listens(world):
    db = world.Session()
    session_lifecycle.open_session(db, db.get(BilliardTable, world.ids.table), None)
    db.flush()
    assert realtime.PENDING_KEY not in db.info                            # no queries, no queue, no work
    db.commit()
    db.close()


def test_the_manager_can_be_replaced_without_touching_callers(world):
    """The Redis hook (I7): callers only know get_realtime()."""
    class Recorder:
        active = True
        def __init__(self): self.messages = []
        async def connect(self, club, ws): raise NotImplementedError
        def disconnect(self, club, conn): pass
        def publish(self, club, message): self.messages.append((club, message))
    recorder = Recorder()
    previous = set_realtime(recorder)
    try:
        world.post(f"/tables/{world.ids.table}/start", json={})
    finally:
        set_realtime(previous)
    assert {m["type"] for _, m in recorder.messages} == {"table.changed", "session.changed"}
    assert {club for club, _ in recorder.messages} == {"c1"}


# ---------------------------------------------------------------- polling still works

def test_polling_endpoint_still_works_without_ws(world):
    assert not world.rt.active
    sid = world.post(f"/tables/{world.ids.table}/start", json={}).json()["session_id"]
    rows = world.get("/tables/active").json()
    assert [r["table_id"] if "table_id" in r else r["id"] for r in rows][0] == world.ids.table
    assert world.post(f"/sessions/{sid}/stop").status_code == 200


def test_polling_gives_the_same_answer_while_a_socket_is_open(world):
    quiet = world.get("/tables/active").json()
    with open_ws(world) as ws:
        ws.receive_json()
        assert world.get("/tables/active").json() == quiet
