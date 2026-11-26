# app/billiard/services/table_lifecycle.py
# The ONLY place that writes BilliardTable.status for play/stop transitions.
# table_service.start_session / session_service.stop_session call these;
# device-event handlers must too. Never assign table.status directly elsewhere.
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.billiard.models import BilliardTable, SessionStatus, TableSession, TableStatus


def mark_playing(table: BilliardTable) -> None:
    if table.is_active is False:
        raise ValueError("Table is inactive")
    if table.status != TableStatus.AVAILABLE:
        raise ValueError(f"Table is {table.status.value}")
    table.status = TableStatus.PLAYING


def mark_available(table: BilliardTable) -> None:
    table.status = TableStatus.AVAILABLE


def _require_free(table: BilliardTable) -> None:
    """Same guard as mark_playing: only an active, AVAILABLE table can change state."""
    if table.is_active is False:
        raise ValueError("Table is inactive")
    if table.status != TableStatus.AVAILABLE:
        raise ValueError(_blocked_message(table))


def _blocked_message(table: BilliardTable) -> str:
    if table.status == TableStatus.PLAYING:
        return "Table is playing, stop its session first"
    return f"Table is {table.status.value}"


def ensure_no_active_session(db: Session, table: BilliardTable) -> None:
    """Check the session record too, not only table.status. Shared by the POS routes and the device
    table_status event, so both refuse to change a table that still has an active session."""
    if db.execute(
        select(TableSession.id).where(TableSession.table_id == table.id, TableSession.status == SessionStatus.ACTIVE)
    ).first():
        raise ValueError("Table has an active session, stop its session first")


def mark_reserved(table: BilliardTable) -> None:
    _require_free(table)
    table.status = TableStatus.RESERVED


def mark_maintenance(table: BilliardTable) -> None:
    """AVAILABLE or RESERVED -> MAINTENANCE.

    A reserved table may go straight to maintenance (it broke before the guest came):
    the reservation is status-only, so leaving RESERVED is what ends it. A PLAYING table
    is never taken over: its session must be stopped first. MAINTENANCE blocks
    mark_playing, so no session can start until release()."""
    if table.status != TableStatus.RESERVED:
        _require_free(table)
    elif table.is_active is False:
        raise ValueError("Table is inactive")
    table.status = TableStatus.MAINTENANCE


def release(table: BilliardTable) -> None:
    """RESERVED / MAINTENANCE -> AVAILABLE. A playing or already free table is refused."""
    if table.is_active is False:
        raise ValueError("Table is inactive")
    if table.status not in (TableStatus.RESERVED, TableStatus.MAINTENANCE):
        raise ValueError(f"Table is {table.status.value}, only a reserved or maintenance table can be released")
    table.status = TableStatus.AVAILABLE


def find_inconsistencies(db: Session) -> list[str]:
    """Drift between table.status and session.status. Empty list = invariant holds."""
    problems: list[str] = []

    has_active = exists().where(
        TableSession.table_id == BilliardTable.id, TableSession.status == SessionStatus.ACTIVE
    )
    for (tid,) in db.execute(
        select(BilliardTable.id).where(BilliardTable.status == TableStatus.PLAYING, ~has_active)
    ):
        problems.append(f"table {tid} is PLAYING but has no active session")

    for sid, tid in db.execute(
        select(TableSession.id, TableSession.table_id)
        .join(BilliardTable, BilliardTable.id == TableSession.table_id)
        .where(TableSession.status == SessionStatus.ACTIVE, BilliardTable.status != TableStatus.PLAYING)
    ):
        problems.append(f"session {sid} is active but table {tid} is not PLAYING")
    return problems