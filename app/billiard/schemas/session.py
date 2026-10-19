# app/billiard/schemas/session.py
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


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

    start_time: datetime
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    hourly_rate: Decimal
    billing_policy: str
    # From the session's pricing snapshot. None / {} for sessions that matched no
    # rule and for sessions created before pricing rules existed.
    pricing_rule_name: Optional[str] = None
    pricing_params: dict[str, Any] = Field(default_factory=dict)

    total_table_fee: Decimal
    total_product_fee: Decimal
    grand_total: Decimal
    items: list[SessionItemResponse]

    payment_state: str
    payment_method: Optional[str] = None      # "cash" | "bank_transfer" | "stripe" | "split"
    payment_reference: Optional[str] = None
    paid_at: Optional[datetime] = None
    amount_paid: Decimal = Decimal("0")       # sum of completed payment lines
    balance_due: Decimal = Decimal("0")       # grand_total - amount_paid
    payments: list["PaymentLineResponse"] = Field(default_factory=list)

    opened_by: Optional[str] = None
    stopped_by: Optional[str] = None
    paid_by: Optional[str] = None


class TransferInstruction(BaseModel):
    """What to show the customer for a bank transfer (VietQR)."""
    bank_code: Optional[str] = None
    account_no: Optional[str] = None
    account_name: Optional[str] = None
    amount: Decimal
    memo: str
    qr_payload: Optional[str] = None      # render as a QR code; None if no bank account is configured
    qr_image_url: Optional[str] = None
    expires_at: Optional[datetime] = None


class PaymentLineResponse(BaseModel):
    id: int
    method: str
    amount: Decimal
    status: str
    cash_tendered: Optional[Decimal] = None
    change_given: Optional[Decimal] = None
    payment_reference: Optional[str] = None
    note: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    voided_at: Optional[datetime] = None
    void_reason: Optional[str] = None
    transfer: Optional[TransferInstruction] = None   # only for a pending bank_transfer line


class PaymentLineInput(BaseModel):
    method: Literal["cash", "bank_transfer"]
    amount: Decimal = Field(..., gt=0)
    cash_tendered: Optional[Decimal] = Field(None, gt=0, description="Cash only: amount handed over")
    note: Optional[str] = Field(None, max_length=255)

    @model_validator(mode="after")
    def _tendered_only_for_cash(self):
        if self.cash_tendered is not None and self.method != "cash":
            raise ValueError("cash_tendered is only valid for cash")
        return self


class PaySessionRequest(BaseModel):
    """Pay in one go (`payment_method`) or split the bill (`payments`), never both.

    The bill total is NEVER accepted from the client: it is session.grand_total.
    For a split, the line amounts are allocations and must add up exactly to the amount due.
    """
    payment_method: Optional[Literal["cash", "bank_transfer", "stripe"]] = None
    cash_tendered: Optional[Decimal] = Field(None, gt=0, description="With payment_method=cash")
    payments: Optional[list[PaymentLineInput]] = Field(None, min_length=1, max_length=6)

    @model_validator(mode="after")
    def _one_style(self):
        if (self.payment_method is None) == (self.payments is None):
            raise ValueError("Send exactly one of payment_method or payments")
        if self.cash_tendered is not None and self.payment_method != "cash":
            raise ValueError("cash_tendered is only valid with payment_method=cash")
        return self


class ConfirmTransferRequest(BaseModel):
    note: Optional[str] = Field(None, max_length=255)


class CancelPaymentLineRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=255)


class VoidPaymentLineRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=255)


class PaymentEventResponse(BaseModel):
    id: int
    line_id: Optional[int] = None
    event_type: str
    actor_id: Optional[int] = None
    data: Optional[dict[str, Any]] = None
    created_at: datetime


class PayResponse(BillResponse):
    # Gateway payload (e.g. Stripe client_secret) when the payment is not instant.
    gateway: Optional[dict[str, Any]] = None


BillResponse.model_rebuild()
PayResponse.model_rebuild()
