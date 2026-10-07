# app/billiard/services/game_service.py
# Game rules only. Billing is NOT touched here: starting/finishing a game never
# changes the session timer, hourly rate or totals (Rule 4 / Rule 15).
#
# Locking: every mutation takes the SESSION row lock first (same order as
# add_item / stop / pay), so score changes serialize against stop_session.
# Services flush; routes commit.
import logging
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billiard.models import GameStatus, SessionStatus, TableGame, TableSession
from app.billiard.services import game_lifecycle
from app.billiard.services.session_service import session_service
from app.user.models.user import User

logger = logging.getLogger(__name__)

_SCORE_COLUMNS = {"A": TableGame.player_a_score, "B": TableGame.player_b_score}


class GameService:

    # ── helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _lock_game(db: Session, game_id: int, user: User) -> tuple[TableSession, TableGame]:
        """Resolve game -> session, lock the session (tenant-checked, 404 for
        other tenants), then re-read the game so we never act on stale scores."""
        session_id = db.execute(
            select(TableGame.session_id).where(TableGame.id == game_id)
        ).scalar_one_or_none()
        if session_id is None:
            raise HTTPException(404, "Game not found")

        session = session_service.get_locked_session(db, session_id, user)
        game = db.get(TableGame, game_id)
        db.refresh(game)   # pick up changes committed while we waited for the lock
        return session, game

    @staticmethod
    def _require_active(session: TableSession, game: TableGame) -> None:
        if session.status != SessionStatus.ACTIVE:
            raise HTTPException(409, "Session is not active")
        if game.status != GameStatus.ACTIVE:
            raise HTTPException(409, "Game is not active")

    # ── queries ──────────────────────────────────────────────────────────
    @staticmethod
    def list_games(db: Session, session_id: int, user: User) -> list[TableGame]:
        session = session_service.get_session(db, session_id, user)
        return list(session.games)   # ordered by game_number via the relationship

    # ── commands ─────────────────────────────────────────────────────────
    @staticmethod
    def start_game(
        db: Session, session_id: int, user: User, at: Optional[datetime] = None
    ) -> TableGame:
        session = session_service.get_locked_session(db, session_id, user)
        try:
            return game_lifecycle.open_game(db, session, at)
        except ValueError as e:
            raise HTTPException(409, str(e))
        except IntegrityError:
            db.rollback()   # lost a race with a concurrent start
            raise HTTPException(409, "Session already has an active game")

    @staticmethod
    def change_score(
        db: Session, game_id: int, player: str, delta: int, user: User
    ) -> TableGame:
        session, game = GameService._lock_game(db, game_id, user)
        GameService._require_active(session, game)

        col = _SCORE_COLUMNS[player]
        # Single atomic UPDATE. The `>= 0` guard makes "never negative" hold even
        # on SQLite (where the row lock is a no-op) and under concurrent presses.
        result = db.execute(
            update(TableGame)
            .where(
                TableGame.id == game.id,
                TableGame.status == GameStatus.ACTIVE,
                col + delta >= 0,
            )
            .values({col: col + delta})
        )
        if result.rowcount == 0:
            raise HTTPException(409, "Score cannot go below 0")

        db.refresh(game)
        # Audit trail for API-originated changes. Device-originated ones are
        # additionally recorded as DeviceEvent rows by the event service.
        logger.info(
            "score_change game=%s player=%s delta=%+d -> %s:%s by user=%s",
            game.id, player, delta, game.player_a_score, game.player_b_score, user.id,
        )
        return game

    @staticmethod
    def reset_score(db: Session, game_id: int, user: User) -> TableGame:
        session, game = GameService._lock_game(db, game_id, user)
        GameService._require_active(session, game)

        game.player_a_score = 0
        game.player_b_score = 0
        db.flush()
        logger.info("score_reset game=%s by user=%s", game.id, user.id)
        return game

    @staticmethod
    def finish_game(
        db: Session, game_id: int, user: User, at: Optional[datetime] = None
    ) -> TableGame:
        session, game = GameService._lock_game(db, game_id, user)
        GameService._require_active(session, game)
        return game_lifecycle.close_game(db, game, at)

    @staticmethod
    def new_game(
        db: Session, game_id: int, user: User, at: Optional[datetime] = None
    ) -> tuple[TableGame, TableGame]:
        """NEW GAME: complete the current game, open the next one at 0:0.
        The session (and its billing timer) is untouched."""
        session, game = GameService._lock_game(db, game_id, user)
        GameService._require_active(session, game)

        finished = game_lifecycle.close_game(db, game, at)   # flushes
        try:
            started = game_lifecycle.open_game(db, session, at)
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Session already has an active game")
        return finished, started


game_service = GameService()
