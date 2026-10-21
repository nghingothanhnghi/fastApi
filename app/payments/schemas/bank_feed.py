# app/payments/schemas/bank_feed.py
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class BankTransactionResponse(BaseModel):
    id: int
    provider: str
    external_id: str
    gateway: Optional[str] = None
    account_number: Optional[str] = None
    transfer_type: Optional[str] = None
    amount: Decimal
    content: Optional[str] = None
    code: Optional[str] = None
    reference_code: Optional[str] = None
    transaction_date: Optional[datetime] = None
    status: str
    reason: Optional[str] = None
    order_id: Optional[int] = None
    line_id: Optional[int] = None
    handled_by_id: Optional[int] = None
    handled_at: Optional[datetime] = None
    note: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AssignBankTransactionRequest(BaseModel):
    line_id: int


class IgnoreBankTransactionRequest(BaseModel):
    note: Optional[str] = Field(None, max_length=255)
