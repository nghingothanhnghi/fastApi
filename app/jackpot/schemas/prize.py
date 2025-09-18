from pydantic import BaseModel

class PrizeResultSchema(BaseModel):
    ticket_id: int
    category: str
    prize_value: float
