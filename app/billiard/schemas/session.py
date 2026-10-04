# app/billiard/schemas/session.py
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class StartSessionResponse(BaseModel):
    session_id: int
    table_id: int
    start_time: datetime
    opened_by: str


class AddSessionItemRequest(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    quantity: int = Field(..., gt=0, le=1000)


class SessionItemResponse(BaseModel):
    id: int
    product_id: int
    variant_id: Optional[int] = None
    product_name: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal


class BillResponse(BaseModel):
    """Bill after STOP and receipt after PAY: same shape, built only from session snapshots."""
    session_id: int
    table_id: int
    table_name: str
    currency: str

    start_time: datetime
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    hourly_rate: Decimal
    billing_policy: str

    total_table_fee: Decimal
    total_product_fee: Decimal
    grand_total: Decimal
    items: list[SessionItemResponse]

    payment_state: str
    payment_method: Optional[str] = None
    payment_reference: Optional[str] = None
    paid_at: Optional[datetime] = None

    opened_by: Optional[str] = None
    stopped_by: Optional[str] = None
    paid_by: Optional[str] = None


class PaySessionRequest(BaseModel):
    # Amount is NEVER accepted from the client: it is session.grand_total.
    payment_method: Literal["cash", "bank_transfer", "stripe"]


class PayResponse(BillResponse):
    # Gateway payload (e.g. Stripe client_secret) when the payment is not instant.
    gateway: Optional[dict[str, Any]] = None