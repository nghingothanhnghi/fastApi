# app/jackpot/schemas/rules.py
from pydantic import BaseModel
from typing import List

class JackpotRuleSchema(BaseModel):
    min_price: int
    number_range: List[int]
    jackpot1_min: int
    jackpot2_min: int
    draw_days: List[str]
    draw_time: str

    model_config = {
        "from_attributes": True
    }
