# app/jackpot/schemas/ticket.py
from pydantic import BaseModel
from typing import List
from enum import Enum

class PlayType(str, Enum):
    basic = "basic"
    bao5 = "bao5"
    bao7 = "bao7"
    bao8 = "bao8"
    bao9 = "bao9"

class TicketCreateSchema(BaseModel):
    user_id: int
    numbers: List[int]
    play_type: PlayType

class TicketSchema(BaseModel):
    id: int
    user_id: int
    numbers: List[int]
    play_type: PlayType
    draw_id: int

    model_config = {
        "from_attributes": True
    }
