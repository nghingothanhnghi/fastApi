# app/payments/schemas/payment.py
from pydantic import BaseModel
from typing import Optional, Dict
from datetime import datetime
from enum import Enum


class PaymentStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentCreate(BaseModel):
    user_id: int
    client_id: str
    provider: str
    amount: float
    currency: str = "VND"
    reference_id: str
    metadata: Optional[Dict] = None


class PaymentUpdate(BaseModel):
    status: PaymentStatus
    metadata: Optional[Dict] = None


class PaymentOut(BaseModel):
    id: int
    user_id: int
    client_id: str
    provider: str
    amount: float
    currency: str
    status: PaymentStatus
    reference_id: str
    metadata: Optional[Dict]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {
        "from_attributes": True
    }
