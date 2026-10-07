# app/billiard/schemas/game.py
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.billiard.models.game import GameStatus


class GameResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    game_number: int
    start_time: datetime
    end_time: Optional[datetime] = None
    player_a_score: int
    player_b_score: int
    status: GameStatus


class ScoreChangeRequest(BaseModel):
    player: Literal["A", "B"]
    # Small bound: a button press is +/-1. Larger values are almost certainly bugs.
    delta: int = Field(..., ge=-10, le=10)

    @field_validator("delta")
    @classmethod
    def _non_zero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("delta must not be 0")
        return v


class NewGameResponse(BaseModel):
    finished: GameResponse
    started: GameResponse
