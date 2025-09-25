# app/jackpot/schemas/analytics.py
from pydantic import BaseModel
from typing import List
from datetime import datetime


class TicketCountByDrawItem(BaseModel):
    draw_id: int
    draw_date: datetime
    ticket_count: int


class NumberCount(BaseModel):
    number: int
    count: int


class NumberFrequencyResponse(BaseModel):
    hot_numbers: List[NumberCount]
    cold_numbers: List[NumberCount]


class SalesSummaryResponse(BaseModel):
    total_tickets: int
    unit_price: int
    total_revenue: int


class NextSuggestionResponse(BaseModel):
    suggested_numbers: List[int]
    strategy: str