# app/jackpot/schemas/ticket.py
from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

from app.jackpot.schemas.prize import PrizeResultSchema

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

class TicketWithPrizeSchema(BaseModel):
    ticket: TicketSchema
    prize: Optional[PrizeResultSchema]

    model_config = {
        "from_attributes": True
    }    
