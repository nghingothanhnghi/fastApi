# app/jackpot/schemas/prize.py
from pydantic import BaseModel

class PrizeProbabilities(BaseModel):
    jackpot: float
    five_plus_bonus: float
    four_numbers: float
    three_numbers: float

class PrizeResultSchema(BaseModel):
    id: int
    ticket_id: int
    category: str
    prize_value: float


class PrizeHistorySummarySchema(BaseModel):
    totalJackpot1: int
    totalJackpot2: int
    totalFirst: int
    totalSecond: int
    totalThird: int
    totalPrizeValue: float
    probabilities: PrizeProbabilities