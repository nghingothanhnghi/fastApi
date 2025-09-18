from pydantic import BaseModel
from typing import List
from datetime import datetime

class DrawSchema(BaseModel):
    id: int
    draw_date: datetime
    numbers: List[int]
    bonus_number: int

    model_config = {
        "from_attributes": True
    }
