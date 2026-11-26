# app/billiard/services/event_service.py
# Device event intake: idempotency (event_id), ordering (device_seq), and apply.
#
# RECONCILIATION RULE (decided with the owner):
#   SCORES: the device wins. While offline the ESP32 is the source of truth for
#   the scoreboard; the server records what the device reports, even if the POS
#   showed something else, and notes the overwritten value on the event.
#   BILLING/PAYMENT/PRICES: the server stays authoritative (never read from events).
#
# TRANSACTIONS: like payment_service, this service COMMITS, once per event.
# Each event is acknowledged independently, so a poison event can never roll
# back events already acknowledged earlier in the same batch.
#
#   SESSIONS/GAMES: the device's session/game MAPS TO the server's. If the server
#   already has an active session (or game) for that table (e.g. the POS started
#   it), the device's LOCAL-S/LOCAL-G id is mapped to it instead of creating a
#   duplicate. Official start/end times are the device's (clamped: never in the
#   future, never before the start); the SERVER still computes the fee.
#
# Implemented handlers: heartbeat, score_change, score_reset, game_end,
# session_start, session_stop, game_start, new_game, time_extend, table_status,
# button_press, device_error. A type with no handler would be stored as REJECTED with a
# clear message, never silently dropped.
#
# WHAT AN EVENT MAY CHANGE (three separate things, never mixed):
#   - what was purchased   -> TableSession.package_snapshot: written only at session start / billing review
#   - what is owed         -> total_* / grand_total / pricing_snapshot: written only by session_lifecycle
#   - what physically happened -> the DeviceEvent row and the scoreboard / countdown / table status
# time_extend moves ends_at and nothing else, so it cannot reset a package, its free-product
# allowance, a billing review or the bill.
import logging
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billiard.models import (
    BilliardDevice, BilliardTable, DeviceEvent, DeviceEventStatus, DeviceEventType,
    DeviceLocalIdMap, DeviceStatus, GameStatus, SessionStatus, TableGame, TableSession,
)
from app.billiard.schemas.event import DeviceEventIn, EventBatchResult, EventRef
from app.billiard.services import game_lifecycle, session_lifecycle, table_lifecycle
from app.billiard.services.package_service import package_service

from app.billiard import config
from app.billiard.utils.billing import as_utc

logger = logging.getLogger(__name__)


class EventRejected(Exception):
    """Invalid or unresolvable event. Stored as REJECTED, kept for inspection."""


class EventConflict(Exception):
    """Contradicts server state in a way the rule can't settle. Stored as CONFLICT."""


# ── helpers ──────────────────────────────────────────────────────────────
def _event_time(ev: DeviceEventIn) -> Optional[datetime]:
    """Device timestamp only when its clock was valid; otherwise let the
    lifecycle helpers use server time."""
    if ev.timestamp is None or ev.clock_synced is False:
       return None
    return _check_device_time(ev.timestamp)

def _check_device_time(ts: datetime) -> datetime:
    now = datetime.now(timezone.utc)
    ts = as_utc(ts)
    ahead = (ts - now).total_seconds()
    if ahead > config.MAX_CLOCK_AHEAD_SECONDS:
        raise EventRejected(
            f"Device clock is {int(ahead)}s ahead of server time "
            f"(limit {config.MAX_CLOCK_AHEAD_SECONDS}s); resync the device clock")
    if ts < now - timedelta(hours=config.MAX_OFFLINE_HOURS):
        raise EventRejected(
            f"Device timestamp is older than {config.MAX_OFFLINE_HOURS}h; "
            "too old to bill from the device clock")
    return ts

def _scores(data: dict) -> tuple[int, int]:
    try:
        a, b = int(data["score_a"]), int(data["score_b"])
    except (KeyError, TypeError, ValueError):
        raise EventRejected("score_a and score_b are required integers")
    if a < 0 or b < 0:
        raise EventRejected("Scores cannot be negative")
    return a, b


def _resolve_game(db: Session, device_pk: int, client_id: str, ev: DeviceEventIn) -> TableGame:
    """Find the target game: server game_id > LOCAL game id mapping > table's active game.
    Then lock its session and re-read the game. Other tenants get the same
    message as 'not found' (don't leak that the id exists)."""
    game: Optional[TableGame] = None
    try:
        if ev.data.get("game_id") is not None:
            game = db.get(TableGame, int(ev.data["game_id"]))
        elif ev.local_game_id:
            gid = db.execute(
                select(DeviceLocalIdMap.game_id).where(
                    DeviceLocalIdMap.device_pk == device_pk,
                    DeviceLocalIdMap.kind == "game",
                    DeviceLocalIdMap.local_id == ev.local_game_id,
                )
            ).scalar_one_or_none()
            game = db.get(TableGame, gid) if gid else None
        elif ev.table_id is not None:
            session = db.execute(
                select(TableSession).where(
                    TableSession.table_id == ev.table_id, TableSession.status == SessionStatus.ACTIVE
                )
            ).scalar_one_or_none()
            game = game_lifecycle.get_active_game(db, session.id) if session else None
    except (TypeError, ValueError):
        raise EventRejected("Invalid game reference")

    if game is None:
        raise EventRejected("Game not found")

    session = db.execute(
        select(TableSession).where(TableSession.id == game.session_id).with_for_update()
    ).scalar_one()
    if session.table.client_id != client_id:
        raise EventRejected("Game not found")
    db.refresh(game)
    return game


def _apply_scores(db: Session, game: TableGame, a: int, b: int) -> Optional[dict]:
    """Device wins. Returns an audit note when the server value was overwritten."""
    previous = game_lifecycle.set_scores(db, game, a, b)
    if previous != (a, b):
        return {"server": list(previous), "device": [a, b]}
    return None


# ── handlers: (db, device_pk, client_id, ev) -> optional audit note ──────
def _h_heartbeat(db, device_pk, client_id, ev):
    # last_seen/status are already updated by authentication
    version = ev.data.get("firmware_version")
    if version:
        db.get(BilliardDevice, device_pk).firmware_version = str(version)[:30]
    return None


def _h_score_change(db, device_pk, client_id, ev):
    game = _resolve_game(db, device_pk, client_id, ev)
    if game.status == GameStatus.CANCELLED:
        raise EventConflict("Game was cancelled on the server")
    a, b = _scores(ev.data)
    return _apply_scores(db, game, a, b)


def _h_score_reset(db, device_pk, client_id, ev):
    game = _resolve_game(db, device_pk, client_id, ev)
    if game.status == GameStatus.CANCELLED:
        raise EventConflict("Game was cancelled on the server")
    return _apply_scores(db, game, 0, 0)


def _h_game_end(db, device_pk, client_id, ev):
    game = _resolve_game(db, device_pk, client_id, ev)
    if game.status == GameStatus.CANCELLED:
        raise EventConflict("Game was cancelled on the server")
    note = None
    if "score_a" in ev.data or "score_b" in ev.data:
        a, b = _scores(ev.data)               # final score reported by the device
        note = _apply_scores(db, game, a, b)
    if game.status == GameStatus.ACTIVE:
        game_lifecycle.close_game(db, game, _event_time(ev))
    return note                                # already COMPLETED: idempotent no-op


# ── LOCAL id mapping (LOCAL-S-… / LOCAL-G-… -> server ids) ───────────────
def _mapped(db: Session, device_pk: int, kind: str, local_id: Optional[str]) -> Optional[int]:
    if not local_id:
        return None
    col = DeviceLocalIdMap.session_id if kind == "session" else DeviceLocalIdMap.game_id
    return db.execute(
        select(col).where(
            DeviceLocalIdMap.device_pk == device_pk,
            DeviceLocalIdMap.kind == kind,
            DeviceLocalIdMap.local_id == local_id,
        )
    ).scalar_one_or_none()


def _map_local(db: Session, device_pk: int, kind: str, local_id: Optional[str], target_id: int) -> None:
    if not local_id or _mapped(db, device_pk, kind, local_id) is not None:
        return
    db.add(DeviceLocalIdMap(
        device_pk=device_pk, kind=kind, local_id=local_id,
        session_id=target_id if kind == "session" else None,
        game_id=target_id if kind == "game" else None,
    ))
    db.flush()


def _resolve_session(db: Session, device_pk: int, client_id: str, ev: DeviceEventIn) -> TableSession:
    """server session_id > LOCAL session id mapping > table's active session; then lock it."""
    session_id: Optional[int] = None
    try:
        if ev.data.get("session_id") is not None:
            session_id = int(ev.data["session_id"])
        elif ev.local_session_id:
            session_id = _mapped(db, device_pk, "session", ev.local_session_id)
        elif ev.table_id is not None:
            session_id = db.execute(
                select(TableSession.id).where(
                    TableSession.table_id == ev.table_id, TableSession.status == SessionStatus.ACTIVE
                )
            ).scalar_one_or_none()
    except (TypeError, ValueError):
        raise EventRejected("Invalid session reference")

    session = None
    if session_id is not None:
        session = db.execute(
            select(TableSession).where(TableSession.id == session_id).with_for_update()
        ).scalar_one_or_none()
    if session is None or session.table.client_id != client_id:
        raise EventRejected("Session not found")
    return session


def _lock_table(db: Session, client_id: str, table_id: Optional[int]) -> BilliardTable:
    if table_id is None:
        raise EventRejected("table_id is required")
    table = db.execute(
        select(BilliardTable).where(BilliardTable.id == table_id).with_for_update()
    ).scalar_one_or_none()
    if table is None or table.client_id != client_id:
        raise EventRejected("Table not found")
    return table


def _apply_final_scores_if_present(db: Session, session: TableSession, data: dict) -> Optional[dict]:
    if "score_a" not in data and "score_b" not in data:
        return None
    a, b = _scores(data)
    game = game_lifecycle.get_active_game(db, session.id)
    return _apply_scores(db, game, a, b) if game else None


# ── session / game lifecycle handlers ────────────────────────────────────
def _h_session_start(db, device_pk, client_id, ev):
    table = _lock_table(db, client_id, ev.table_id)
    already = _mapped(db, device_pk, "session", ev.local_session_id)
    if already is not None:
        return {"already_mapped_session_id": already}

    active = db.execute(
        select(TableSession).where(
            TableSession.table_id == table.id, TableSession.status == SessionStatus.ACTIVE
        ).with_for_update()
    ).scalar_one_or_none()
    if active is not None:                       # device's session MAPS TO the server's
        _map_local(db, device_pk, "session", ev.local_session_id, active.id)
        return {"adopted_session_id": active.id}

    package, review_reason = None, None
    package_id = (ev.data or {}).get("package_id")
    if package_id is not None:
        # The device already started playing, so the event is accepted and the real session is opened. If the
        # package cannot be applied the session is flagged for BILLING REVIEW (payment blocked until a cashier
        # assigns a package or confirms normal pricing) instead of silently billing at the normal rate.
        valid_type = isinstance(package_id, int) and not isinstance(package_id, bool)
        package = package_service.find_for_club(db, package_id, client_id) if valid_type else None
        if not valid_type:
            review_reason = "Invalid package_id"
        elif package is None:                       # unknown and other club's look the same: never leak other clubs
            review_reason = "Package not found"
        elif not package.is_active:
            review_reason = "Package is not available"
        if review_reason:
            package = None

    try:
        session = session_lifecycle.open_session(db, table, None, _event_time(ev), package=package)
    except ValueError as e:                      # maintenance / inactive / reserved table
        raise EventConflict(str(e))
    _map_local(db, device_pk, "session", ev.local_session_id, session.id)
    if review_reason:
        session_lifecycle.flag_billing_review(session, package_id, review_reason)
        return {"billing_review_required": review_reason, "requested_package_id": session.requested_package_id}
    return None


def _h_session_stop(db, device_pk, client_id, ev):
    session = _resolve_session(db, device_pk, client_id, ev)
    if session.status == SessionStatus.CANCELLED:
        raise EventConflict("Session was cancelled on the server")
    if session.status == SessionStatus.COMPLETED:
        return {"already_completed_session_id": session.id}   # server billing stays as is

    table = db.execute(
        select(BilliardTable).where(BilliardTable.id == session.table_id).with_for_update()
    ).scalar_one()
    note = _apply_final_scores_if_present(db, session, ev.data)   # device wins on scores
    session_lifecycle.finalize_stop(db, session, table, None, _event_time(ev))
    return note


def _h_game_start(db, device_pk, client_id, ev):
    session = _resolve_session(db, device_pk, client_id, ev)
    if session.status != SessionStatus.ACTIVE:
        raise EventConflict("Session is not active on the server")
    already = _mapped(db, device_pk, "game", ev.local_game_id)
    if already is not None:
        return {"already_mapped_game_id": already}

    active = game_lifecycle.get_active_game(db, session.id)
    if active is not None:                       # device's game MAPS TO the server's
        _map_local(db, device_pk, "game", ev.local_game_id, active.id)
        return {"adopted_game_id": active.id}

    game = game_lifecycle.open_game(db, session, _event_time(ev))
    _map_local(db, device_pk, "game", ev.local_game_id, game.id)
    return None


def _h_new_game(db, device_pk, client_id, ev):
    """ev.local_game_id / game_id = the game being finished;
    data.new_local_game_id = the id the device gave the next game."""
    game = _resolve_game(db, device_pk, client_id, ev)
    session = db.get(TableSession, game.session_id)
    if game.status == GameStatus.CANCELLED:
        raise EventConflict("Game was cancelled on the server")
    if session.status != SessionStatus.ACTIVE:
        raise EventConflict("Session is not active on the server")

    note = None
    if "score_a" in ev.data or "score_b" in ev.data:
        a, b = _scores(ev.data)                  # final score of the finished game
        note = _apply_scores(db, game, a, b)

    at = _event_time(ev)
    if game.status == GameStatus.ACTIVE:
        game_lifecycle.close_game(db, game, at)

    new_local = ev.data.get("new_local_game_id")
    if _mapped(db, device_pk, "game", new_local) is not None:
        return note

    nxt = game_lifecycle.get_active_game(db, session.id)
    adopted = nxt is not None
    if nxt is None:
        nxt = game_lifecycle.open_game(db, session, at)
    _map_local(db, device_pk, "game", new_local, nxt.id)
    if adopted:
        note = {**(note or {}), "adopted_game_id": nxt.id}
    return note


# ── time_extend / table_status / button_press / device_error ─────────────
MAX_EXTEND_MINUTES = 480          # same limit as POST /sessions/{id}/extend


def _int_field(data: dict, key: str, low: int, high: int) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not (low <= value <= high):
        raise EventRejected(f"{key} must be a whole number between {low} and {high}")
    return value


def _h_time_extend(db, device_pk, client_id, ev):
    """data.minutes (1-480): push the countdown (ends_at) of the table's ACTIVE session forward.
    Only ends_at changes. The base is the device time of the press (clock rules apply), so a press that
    reaches the server late still gives the customer the time from when it was pressed."""
    at = _event_time(ev)
    minutes = _int_field(ev.data, "minutes", 1, MAX_EXTEND_MINUTES)
    session = _resolve_session(db, device_pk, client_id, ev)      # no active session for the table: rejected
    if session.status != SessionStatus.ACTIVE:
        raise EventConflict("Session is not active on the server")
    session_lifecycle.extend_session(session, minutes, now=at)
    db.flush()
    return {"ends_at": as_utc(session.ends_at).isoformat()}


_TABLE_STATUS_CHANGES = {
    "reserved": table_lifecycle.mark_reserved,
    "maintenance": table_lifecycle.mark_maintenance,
    "available": table_lifecycle.release,
}


def _h_table_status(db, device_pk, client_id, ev):
    """data.status in reserved | maintenance | available, through the same table_lifecycle functions as the POS.

    STALE PROTECTION (optimistic concurrency): data.expected_version is the table's `status_version` the device last
    saw (GET /controller/state). If the table has changed since (the POS reserved it, a session started...), the
    version differs and the event is a CONFLICT: it is logged with both versions and NOT applied, so a delayed device
    event can never overwrite a newer change. If the table ALREADY has the reported status the event is a harmless
    no-op that is accepted (idempotent; it never stalls the device's cursor), whatever its version.
    `playing` is refused: only a session start can make a table playing. A table with an active session is a conflict."""
    _event_time(ev)        # a future-dated or too-old status change is not applied
    status = ev.data.get("status")
    if status == "playing":
        raise EventRejected("A table becomes playing only when a session starts (session_start)")
    change = _TABLE_STATUS_CHANGES.get(status) if isinstance(status, str) else None
    if change is None:
        raise EventRejected("status must be one of: reserved, maintenance, available")
    expected = _int_field(ev.data, "expected_version", 0, 2**31 - 1)
    table = _lock_table(db, client_id, ev.table_id)
    current = table.status_version or 0
    if table.status.value == status:
        return {"already": status, "status_version": current}
    if expected != current:
        raise EventConflict(
            f"Stale table_status: the device saw version {expected} but the table is now {table.status.value} "
            f"(version {current}). Not applied; read GET /controller/state and decide again")
    previous = table.status.value
    try:
        table_lifecycle.ensure_no_active_session(db, table)
        change(table)
    except ValueError as e:
        raise EventConflict(str(e))
    db.flush()
    return {"previous": previous, "status_version": table.status_version}


def _button_score(delta_a: int, delta_b: int):
    """A score button: +/-1 on the server's current score of the active game (never below 0).
    Firmware should also send score_change with the absolute score so the two stay in sync."""
    def handler(db, device_pk, client_id, ev):
        game = _resolve_game(db, device_pk, client_id, ev)
        if game.status == GameStatus.CANCELLED:
            raise EventConflict("Game was cancelled on the server")
        a = max(game.player_a_score + delta_a, 0)
        b = max(game.player_b_score + delta_b, 0)
        game_lifecycle.set_scores(db, game, a, b)
        return {"score": [a, b]}
    return handler


# The ONE place that says what each controller button means. Each entry reuses an existing handler.
BUTTON_ACTIONS: dict[str, Callable] = {
    "score_a_up": _button_score(1, 0),
    "score_a_down": _button_score(-1, 0),
    "score_b_up": _button_score(0, 1),
    "score_b_down": _button_score(0, -1),
    "reset_score": _h_score_reset,
    "new_game": _h_new_game,
    "end_game": _h_game_end,
}


def _h_button_press(db, device_pk, client_id, ev):
    """data.action -> BUTTON_ACTIONS. An unknown action is rejected with a message, never dropped."""
    _event_time(ev)
    action = ev.data.get("action")
    handler = BUTTON_ACTIONS.get(action) if isinstance(action, str) else None
    if handler is None:
        raise EventRejected(f"Unknown button action {str(action)[:40]!r}; known: {', '.join(sorted(BUTTON_ACTIONS))}")
    note = handler(db, device_pk, client_id, ev)
    return {"button": action, **(note or {})}


def _clean(value, limit: int) -> Optional[str]:
    text = str(value).strip()[:limit] if value is not None else ""
    return text or None


def _h_device_error(db, device_pk, client_id, ev):
    """A fault report: always stored as processed (rejecting it would hide the fault). The latest one is
    copied onto the device row so managers see it in GET /controller/status. last_error_at is the server's
    receive time; the device's own timestamp stays on the event row."""
    code = _clean(ev.data.get("code"), 64) or "unspecified"
    message = _clean(ev.data.get("message"), 200)
    device = db.get(BilliardDevice, device_pk)
    device.last_error = (f"{code}: {message}" if message else code)[:255]
    device.last_error_at = datetime.now(timezone.utc)
    return {"code": code, "message": message}


HANDLERS: dict[DeviceEventType, Callable] = {
    DeviceEventType.HEARTBEAT: _h_heartbeat,
    DeviceEventType.SCORE_CHANGE: _h_score_change,
    DeviceEventType.SCORE_RESET: _h_score_reset,
    DeviceEventType.GAME_END: _h_game_end,
    DeviceEventType.SESSION_START: _h_session_start,
    DeviceEventType.SESSION_STOP: _h_session_stop,
    DeviceEventType.GAME_START: _h_game_start,
    DeviceEventType.NEW_GAME: _h_new_game,
    DeviceEventType.TIME_EXTEND: _h_time_extend,
    DeviceEventType.TABLE_STATUS: _h_table_status,
    DeviceEventType.BUTTON_PRESS: _h_button_press,
    DeviceEventType.DEVICE_ERROR: _h_device_error,
}


# ── intake ───────────────────────────────────────────────────────────────
def _row(device_pk: int, client_id: str, table_id: Optional[int], ev: DeviceEventIn,
         status: DeviceEventStatus, error: Optional[str] = None) -> DeviceEvent:
    return DeviceEvent(
        event_id=ev.event_id, device_pk=device_pk, client_id=client_id, table_id=table_id,
        event_type=ev.event, device_seq=ev.device_seq, device_timestamp=ev.timestamp,
        clock_synced=ev.clock_synced, status=status, error=error,
        local_session_id=ev.local_session_id, local_game_id=ev.local_game_id,
        payload=dict(ev.data),
    )


def _valid_table_id(db: Session, client_id: str, table_id: Optional[int]) -> Optional[int]:
    if table_id is None:
        return None
    table = db.get(BilliardTable, table_id)
    return table_id if table and table.client_id == client_id else None


def _process_one(db: Session, device_pk: int, client_id: str, ev: DeviceEventIn) -> tuple[str, Optional[str]]:
    """Returns (outcome, error): accepted | duplicate | rejected | conflict."""
    existing = db.execute(select(DeviceEvent).where(DeviceEvent.event_id == ev.event_id)).scalar_one_or_none()
    if existing is not None:
        if existing.device_pk != device_pk:
            return "rejected", "event_id already used"
        # Only a *processed* event is safe to acknowledge as a duplicate.  A
        # rejected/conflicting event must remain visible to the controller and
        # must not advance its contiguous acknowledgement cursor; otherwise a
        # retry could cause the device to discard an event the server never
        # applied.
        if existing.status == DeviceEventStatus.PROCESSED:
            return "duplicate", None
        outcome = "conflict" if existing.status == DeviceEventStatus.CONFLICT else "rejected"
        return outcome, existing.error or "Event was not applied"

    seq_taken = db.execute(
        select(DeviceEvent.id).where(DeviceEvent.device_pk == device_pk, DeviceEvent.device_seq == ev.device_seq)
    ).first()
    if seq_taken:
        return "rejected", "device_seq already used by another event"

    table_id = _valid_table_id(db, client_id, ev.table_id)
    handler = HANDLERS.get(ev.event)
    failure_status, error = DeviceEventStatus.REJECTED, ""

    try:
        if handler is None:
            raise EventRejected(f"No handler for '{ev.event.value}' yet")
        row = _row(device_pk, client_id, table_id, ev, DeviceEventStatus.RECEIVED)
        db.add(row)
        db.flush()
        note = handler(db, device_pk, client_id, ev)
        row.status = DeviceEventStatus.PROCESSED
        row.processed_at = datetime.now(timezone.utc)
        if note:
            row.payload = {**(row.payload or {}), "reconciled": note}
        db.commit()
        return "accepted", None
    except IntegrityError as e:
        db.rollback()
        existing = db.execute(
            select(DeviceEvent.status, DeviceEvent.error).where(DeviceEvent.event_id == ev.event_id)
        ).one_or_none()
        if existing is not None:
            status, existing_error = existing
            if status == DeviceEventStatus.PROCESSED:
                return "duplicate", None        # lost a race with a concurrent retry
            outcome = "conflict" if status == DeviceEventStatus.CONFLICT else "rejected"
            return outcome, existing_error or "Event was not applied"
        error = f"Database constraint: {e.orig}"
    except EventConflict as e:
        db.rollback()
        failure_status, error = DeviceEventStatus.CONFLICT, str(e)
    except (EventRejected, ValueError) as e:
        db.rollback()
        error = str(e)
    except Exception as e:                      # one bad event must not block the queue
        logger.exception("Device event %s failed", ev.event_id)
        db.rollback()
        error = f"Unexpected error: {e}"

    db.add(_row(device_pk, client_id, table_id, ev, failure_status, error))
    db.commit()                                 # kept for inspection, never auto-deleted
    return ("conflict" if failure_status == DeviceEventStatus.CONFLICT else "rejected"), error


class EventService:

    @staticmethod
    def _advance_contiguous_cursor(db: Session, device_pk: int, current: int) -> int:
        """Return the highest consecutive *processed* sequence number.

        Events can arrive in separate, out-of-order sync batches.  Rechecking
        persisted state after a batch means an earlier gap being filled later
        immediately acknowledges already-processed following events, without
        ever stepping over a rejected or missing event.
        """
        cursor = current
        while True:
            status = db.execute(
                select(DeviceEvent.status).where(
                    DeviceEvent.device_pk == device_pk,
                    DeviceEvent.device_seq == cursor + 1,
                )
            ).scalar_one_or_none()
            if status != DeviceEventStatus.PROCESSED:
                return cursor
            cursor += 1

    @staticmethod
    def ingest(db: Session, device: BilliardDevice, events: list[DeviceEventIn]) -> EventBatchResult:
        device_pk, client_id = device.id, device.client_id
        result = EventBatchResult()
        initial_cursor = device.last_applied_seq

        for ev in sorted(events, key=lambda e: e.device_seq):   # order by seq, NEVER timestamp
            outcome, error = _process_one(db, device_pk, client_id, ev)
            if outcome == "accepted":
                result.accepted.append(ev.event_id)
            elif outcome == "duplicate":
                result.duplicates.append(ev.event_id)
            elif outcome == "conflict":
                result.conflicts.append(EventRef(event_id=ev.event_id, error=error or ""))
            else:
                result.rejected.append(EventRef(event_id=ev.event_id, error=error or ""))

        # Advance only over a contiguous run of PROCESSED rows, so the device
        # never discards an event the server rejected or has not received yet.
        # Re-read after the per-event commits.  ``max`` below makes the cursor
        # monotonic even if two sync requests finish in a different order.
        device = db.get(BilliardDevice, device_pk)
        applied_seq = EventService._advance_contiguous_cursor(
            db, device_pk, max(initial_cursor, device.last_applied_seq)
        )
        device.last_applied_seq = max(device.last_applied_seq, applied_seq)
        device.last_seen = datetime.now(timezone.utc)
        device.status = DeviceStatus.ONLINE
        db.commit()
        result.server_state_version = device.last_applied_seq
        return result


event_service = EventService()
