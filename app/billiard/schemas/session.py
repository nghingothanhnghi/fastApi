# app/billiard/schemas/session.py
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.payments.schemas.order import PaymentLineResponse


class StartSessionRequest(BaseModel):
    """Optional body of POST /tables/{id}/start. No body (or no planned_minutes) = open play."""
    planned_minutes: Optional[int] = Field(default=None, ge=1, le=1440)


class ExtendSessionRequest(BaseModel):
    minutes: int = Field(..., ge=1, le=480)


class StartSessionResponse(BaseModel):
    session_id: int
    table_id: int
    start_time: datetime
    ends_at: Optional[datetime] = None        # set when planned_minutes was sent
    opened_by: str


class AddSessionItemRequest(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    quantity: int = Field(..., gt=0, le=1000)


class CancelSessionRequest(BaseModel):
    """Why the session is cancelled. Required and kept for audit."""
    reason: str = Field(..., min_length=3, max_length=255)

    @field_validator("reason")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("reason must be at least 3 characters")
        return v


class DiscountRequest(BaseModel):
    """Exactly one of amount (fixed, currency units) or percent. amount = 0 removes the discount.
    A reason is required when a discount is applied (audit)."""
    amount: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    percent: Optional[Decimal] = Field(default=None, gt=0, le=100, max_digits=5, decimal_places=2)
    reason: Optional[str] = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _check(self):
        if (self.amount is None) == (self.percent is None):
            raise ValueError("Give either amount or percent, not both")
        if self.reason is not None:
            self.reason = self.reason.strip() or None
        removing = self.amount is not None and self.amount == 0
        if not removing and (self.reason is None or len(self.reason) < 3):
            raise ValueError("reason is required (at least 3 characters) when applying a discount")
        return self


class SessionItemResponse(BaseModel):
    id: int
    product_id: Optional[int] = None
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
    status: str = "completed"                 # active | completed | cancelled

    start_time: datetime
    end_time: Optional[datetime] = None
    ends_at: Optional[datetime] = None        # timed play countdown target; billing does not use it
    duration_minutes: Optional[int] = None
    hourly_rate: Decimal
    billing_policy: str
    # From the session's pricing snapshot. None / {} for sessions that matched no
    # rule and for sessions created before pricing rules existed.
    pricing_rule_name: Optional[str] = None
    pricing_params: dict[str, Any] = Field(default_factory=dict)

    total_table_fee: Decimal
    total_product_fee: Decimal
    discount: Decimal = Decimal("0")          # amount taken off (table fee + products)
    discount_percent: Optional[Decimal] = None  # set when the discount was given as a percent
    discount_reason: Optional[str] = None
    discounted_by: Optional[str] = None
    grand_total: Decimal                      # table fee + products - discount
    items: list[SessionItemResponse]

    payment_state: str
    payment_method: Optional[str] = None      # "cash" | "bank_transfer" | "stripe" | "split"
    payment_reference: Optional[str] = None
    paid_at: Optional[datetime] = None
    amount_paid: Decimal = Decimal("0")       # sum of completed payment lines
    balance_due: Decimal = Decimal("0")       # grand_total - amount_paid
    payments: list[PaymentLineResponse] = Field(default_factory=list)

    opened_by: Optional[str] = None
    stopped_by: Optional[str] = None
    paid_by: Optional[str] = None

    # Only for a cancelled session
    cancelled_at: Optional[datetime] = None
    cancelled_by: Optional[str] = None
    cancel_reason: Optional[str] = None


class PayResponse(BillResponse):
    # Gateway payload (e.g. Stripe client_secret) when the payment is not instant.
    gateway: Optional[dict[str, Any]] = None

