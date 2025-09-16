# app/payments/schemas/payment.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
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
    extra_metadata: Optional[Dict] = None


class PaymentUpdate(BaseModel):
    status: PaymentStatus
    extra_metadata: Optional[Dict] = None


class PaymentOut(BaseModel):
    id: int
    user_id: int
    client_id: str
    provider: str
    amount: float
    currency: str
    status: PaymentStatus
    reference_id: str
    extra_metadata: Optional[Dict]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {
        "from_attributes": True
    }



# ─────────────────────────────
# 🟦 Stripe-Specific Schemas
# ─────────────────────────────

class StripePaymentCreate(BaseModel):
    user_id: int = Field(..., description="User making the payment")
    client_id: str = Field(..., description="Client ID associated with the payment")
    amount: float = Field(..., gt=0, description="Amount to charge")
    currency: str = Field("usd", min_length=3, max_length=3, description="3-letter currency code (default: usd)")
    extra_metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata to attach to payment intent")


class StripePaymentResponse(BaseModel):
    payment: PaymentOut
    stripe: Dict[str, Any]  # Will contain PaymentIntent data from Stripe