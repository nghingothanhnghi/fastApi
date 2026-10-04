# app/billiard/schemas/session.py
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class StartSessionResponse(BaseModel):
    session_id: int
    table_id: int
    start_time: datetime


class AddSessionItemRequest(BaseModel):
    product_id: int
    quantity: int


class SessionItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    unit_price: Decimal
    total_price: Decimal


class StopSessionResponse(BaseModel):
    session_id: int
    table_id: int

    start_time: datetime
    end_time: datetime

    duration_minutes: int

    total_table_fee: Decimal
    total_product_fee: Decimal
    grand_total: Decimal

    items: list[SessionItemResponse]


class PaySessionRequest(BaseModel):
    payment_method: str


class PaymentResponse(BaseModel):
    payment_id: int
    session_id: int

    amount: Decimal
    payment_method: str

    status: str