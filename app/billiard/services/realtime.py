# app/billiard/services/realtime.py
# Realtime updates for the POS (roadmap item I).
#
# Messages carry only a TYPE and IDS. The POS refetches what it needs, so the server stays the only
# authority and no money or customer data travels over the socket:
#   {"type": "table.changed",   "table_id": 3, "version": 18}
#   {"type": "session.changed", "session_id": 41, "table_id": 3}
#   {"type": "game.changed",    "game_id": 77, "session_id": 41}
#   {"type": "device.status",   "device_id": "BILLIARD-CONTROLLER-01", "status": "offline"}
#
# How messages are produced (services stay free of I/O):
#  1. A Session listener watches what is really flushed (tables, sessions, items, games) and queues
#     one message per touched row in session.info. The POS routes, the controller routes and the payment
#     adapter all write through the ORM, so none of them has to call anything.
#  2. publish_after_commit() queues a message by hand (used where the ORM does not see the change, e.g. the
#     watchdog's conditional UPDATE).
#  3. after_commit sends the queue; after_rollback throws it away. Nothing is sent for a failed request.
#
# One room per club (client_id). InProcessRealtime works for ONE worker; the Realtime interface lets a
# Redis pub/sub implementation replace it later (set_realtime) without touching any caller.
import asyncio
import logging
import threading
from typing import Optional, Protocol

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.billiard import config
from app.billiard.models import BilliardTable, SessionItem, TableGame, TableSession

logger = logging.getLogger(__name__)

PENDING_KEY = "billiard_realtime_pending"


# ── message builders (the only place a message is shaped) ────────────────────
def table_changed(table_id: int, version: int) -> dict:
    return {"type": "table.changed", "table_id": table_id, "version": version}


def session_changed(session_id: int, table_id: int) -> dict:
    return {"type": "session.changed", "session_id": session_id, "table_id": table_id}


def game_changed(game_id: int, session_id: int) -> dict:
    return {"type": "game.changed", "game_id": game_id, "session_id": session_id}


def device_status(device_id: str, status: str) -> dict:
    return {"type": "device.status", "device_id": device_id, "status": status}


# ── the interface and the in-process implementation ──────────────────────────
class Realtime(Protocol):
    """What callers and the WebSocket route may rely on. A Redis implementation must offer the same."""

    @property
    def active(self) -> bool: ...                      # is anyone listening? (lets writers skip the work)
    async def connect(self, client_id: str, websocket) -> "Connection": ...
    def disconnect(self, client_id: str, connection: "Connection") -> None: ...
    def publish(self, client_id: str, message: dict) -> None: ...   # thread-safe, never raises


class Connection:
    """One POS socket. The lock keeps the ping task and a broadcast from sending at the same time."""

    def __init__(self, websocket):
        self.websocket = websocket
        self.loop = asyncio.get_running_loop()        # publish() runs in worker threads and hands the send to THIS loop
        self._lock = asyncio.Lock()

    async def send(self, message: dict) -> None:
        async with self._lock:
            await asyncio.wait_for(self.websocket.send_json(message), timeout=config.WS_SEND_TIMEOUT_SECONDS)


class InProcessRealtime:
    def __init__(self) -> None:
        self._rooms: dict[str, set[Connection]] = {}
        self._guard = threading.Lock()

    @property
    def active(self) -> bool:
        return bool(self._rooms)

    async def connect(self, client_id: str, websocket) -> Connection:
        connection = Connection(websocket)
        with self._guard:
            self._rooms.setdefault(client_id, set()).add(connection)
        return connection

    def disconnect(self, client_id: str, connection: Connection) -> None:
        with self._guard:
            room = self._rooms.get(client_id)
            if room is not None:
                room.discard(connection)
                if not room:
                    del self._rooms[client_id]

    def room_size(self, client_id: str) -> int:
        return len(self._rooms.get(client_id, ()))

    def publish(self, client_id: str, message: dict) -> None:
        with self._guard:
            room = list(self._rooms.get(client_id, ()))
        for connection in room:                           # each send is its own task: one slow client delays nobody
            try:
                asyncio.run_coroutine_threadsafe(self._deliver(client_id, connection, message), connection.loop)
            except RuntimeError:                          # that event loop is gone (shutdown)
                logger.debug("Realtime loop closed; message dropped")

    async def _deliver(self, client_id: str, connection: Connection, message: dict) -> None:
        try:
            await connection.send(message)
        except Exception:                                 # dead or too slow: drop it, the others still get it
            self.disconnect(client_id, connection)
            try:
                await connection.websocket.close()
            except Exception:
                pass


_realtime: Realtime = InProcessRealtime()


def get_realtime() -> Realtime:
    return _realtime


def set_realtime(impl: Realtime) -> Realtime:
    """Swap the implementation (a Redis one later, a fresh one per test). Returns the previous one."""
    global _realtime
    previous, _realtime = _realtime, impl
    return previous


# ── queue: publish only after the transaction really committed ────────────────
def _dedupe_key(client_id: str, message: dict) -> tuple:
    return (client_id, message["type"], message.get("table_id"), message.get("session_id"),
            message.get("game_id"), message.get("device_id"))


def publish_after_commit(db: Session, client_id: str, message: dict) -> None:
    """Queue `message` for the club; it is sent when `db` commits and dropped when it rolls back.
    The same thing changed twice in one transaction is sent once, with the latest content."""
    if not client_id or not get_realtime().active:
        return
    db.info.setdefault(PENDING_KEY, {})[_dedupe_key(client_id, message)] = (client_id, message)


@event.listens_for(Session, "after_commit")
def _send_queued(session: Session) -> None:
    pending = session.info.pop(PENDING_KEY, None)
    if not pending:
        return
    realtime = get_realtime()
    for client_id, message in pending.values():
        realtime.publish(client_id, message)


@event.listens_for(Session, "after_rollback")
def _drop_queued(session: Session) -> None:
    session.info.pop(PENDING_KEY, None)


# ── what changed: collected from the flush ───────────────────────────────────
@event.listens_for(Session, "after_flush")
def _collect(session: Session, flush_context) -> None:
    if not get_realtime().active:                         # nobody is connected: no queries, no work
        return
    touched = [*session.new, *session.dirty, *session.deleted]
    if not any(isinstance(o, (BilliardTable, TableSession, SessionItem, TableGame)) for o in touched):
        return

    connection = session.connection()
    clients: dict[int, Optional[str]] = {}               # table_id -> client_id
    sessions: dict[int, Optional[tuple[int, str]]] = {}  # session_id -> (table_id, client_id)

    def club_of_table(table_id):
        if table_id not in clients:
            clients[table_id] = connection.execute(
                select(BilliardTable.client_id).where(BilliardTable.id == table_id)).scalar()
        return clients[table_id]

    def scope_of_session(session_id):
        if session_id not in sessions:
            table_id = connection.execute(
                select(TableSession.table_id).where(TableSession.id == session_id)).scalar()
            club = club_of_table(table_id) if table_id is not None else None
            sessions[session_id] = (table_id, club) if club else None
        return sessions[session_id]

    def changed(obj) -> bool:
        return obj in session.new or obj in session.deleted or session.is_modified(obj, include_collections=False)

    for obj in touched:
        if isinstance(obj, BilliardTable) and changed(obj):
            publish_after_commit(session, obj.client_id, table_changed(obj.id, obj.status_version or 0))
        elif isinstance(obj, TableSession) and changed(obj):
            club = club_of_table(obj.table_id)
            if club:
                publish_after_commit(session, club, session_changed(obj.id, obj.table_id))
        elif isinstance(obj, SessionItem):                # an item change is a change of its session (and bill)
            scope = scope_of_session(obj.session_id)
            if scope:
                publish_after_commit(session, scope[1], session_changed(obj.session_id, scope[0]))
        elif isinstance(obj, TableGame) and changed(obj):
            scope = scope_of_session(obj.session_id)
            if scope:
                publish_after_commit(session, scope[1], game_changed(obj.id, obj.session_id))
