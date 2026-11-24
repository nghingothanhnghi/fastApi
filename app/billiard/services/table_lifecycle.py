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
        raise ValueError(f"Table is {table.status.value}")


def mark_reserved(table: BilliardTable) -> None:
    _require_free(table)
    table.status = TableStatus.RESERVED


def mark_maintenance(table: BilliardTable) -> None:
    _require_free(table)
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