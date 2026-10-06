# app/billiard/models/game.py
# Tenant scope is inherited through session -> table.client_id (no client_id column here).
import enum
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from ._common import enum_col


class GameStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TableGame(Base):
    __tablename__ = "table_games"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("table_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    game_number: Mapped[int] = mapped_column(Integer, nullable=False)

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    player_a_score: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    player_b_score: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    status: Mapped[GameStatus] = mapped_column(
        enum_col(GameStatus), default=GameStatus.ACTIVE, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    session = relationship("TableSession", back_populates="games")

    __table_args__ = (
        UniqueConstraint("session_id", "game_number", name="uq_game_number_per_session"),
        CheckConstraint("player_a_score >= 0 AND player_b_score >= 0", name="ck_game_scores_non_negative"),
        Index(
            "uq_one_active_game_per_session", "session_id", unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )