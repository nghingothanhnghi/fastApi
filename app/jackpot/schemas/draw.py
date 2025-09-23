# app/jackpot/schemas/draw.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from app.jackpot.models.draw import DrawType, DrawStatus


class DrawCreateSchema(BaseModel):
    draw_type: DrawType = DrawType.automatic
    numbers: Optional[List[int]] = None
    bonus_number: Optional[int] = None

class DrawSchema(BaseModel):
    id: int
    draw_date: datetime
    numbers: List[int]
    bonus_number: int

    draw_type: DrawType
    status: DrawStatus

    model_config = {
        "from_attributes": True
    }
