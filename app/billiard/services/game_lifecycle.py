# app/billiard/services/game_lifecycle.py
# The ONLY place that creates games or writes TableGame.status / end_time.
# Mirrors table_lifecycle.py: no imports from other services, so both
# game_service and session_service (stop_session) can use it without a cycle.
# Helpers never commit and never lock; the caller must already hold the
# session row lock (session_service.get_locked_session).
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.billiard.models import GameStatus, SessionStatus, TableGame, TableSession
from app.billiard.utils.billing import as_utc


def _resolve_time(at: Optional[datetime], floor: datetime) -> datetime:
    """UTC timestamp, never earlier than `floor`.

    `at` may come from the ESP32 clock replayed after offline play. A skewed
    device clock must not produce a game that ends before it starts.
    """
    value = as_utc(at) if at else datetime.now(timezone.utc)
    floor = as_utc(floor)
    return value if value >= floor else floor


def get_active_game(db: Session, session_id: int) -> Optional[TableGame]:
    return db.execute(
        select(TableGame).where(
            TableGame.session_id == session_id, TableGame.status == GameStatus.ACTIVE
        )
    ).scalar_one_or_none()


def open_game(db: Session, session: TableSession, at: Optional[datetime] = None) -> TableGame:
    """Create the next game (scores 0:0). Raises ValueError on a broken precondition.

    May raise IntegrityError from the flush if a concurrent request won the
    race (uq_one_active_game_per_session / uq_game_number_per_session).
    """
    if session.status != SessionStatus.ACTIVE:
        raise ValueError("Games can only be started in an active session")
    if get_active_game(db, session.id) is not None:
        raise ValueError("Session already has an active game")

    last_number = db.execute(
        select(func.coalesce(func.max(TableGame.game_number), 0)).where(
            TableGame.session_id == session.id
        )
    ).scalar_one()

    game = TableGame(
        session_id=session.id,
        game_number=last_number + 1,
        start_time=_resolve_time(at, session.start_time),
        status=GameStatus.ACTIVE,
        player_a_score=0,
        player_b_score=0,
    )
    db.add(game)
    db.flush()
    return game


def close_game(
    db: Session, game: TableGame, at: Optional[datetime] = None,
    status: GameStatus = GameStatus.COMPLETED,
) -> TableGame:
    """Finish a game and flush, so the 'one active game' index is free immediately."""
    game.end_time = _resolve_time(at, game.start_time)
    game.status = status
    db.flush()
    return game


def close_active_game(
    db: Session, session: TableSession, at: Optional[datetime] = None
) -> Optional[TableGame]:
    """Used by stop_session: a stopped session must not leave a game running."""
    game = get_active_game(db, session.id)
    if game is None:
        return None
    return close_game(db, game, at)


def set_scores(db: Session, game: TableGame, a: int, b: int) -> tuple[int, int]:
    """Force both scores (device-wins reconciliation). Returns the previous (a, b)."""
    if a < 0 or b < 0:
        raise ValueError("Scores cannot be negative")
    previous = (game.player_a_score, game.player_b_score)
    game.player_a_score, game.player_b_score = a, b
    db.flush()
    return previous