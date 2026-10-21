# app/payments/schemas/order.py
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.payments import config


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


class PayOrderRequest(BaseModel):
    """Pay in one go (`payment_method`) or split the bill (`payments`), never both.

    The bill total is NEVER accepted from the client: it comes from the business that owns the
    order. For a split, the line amounts are allocations and must add up exactly to the amount due.
    """
    payment_method: Optional[Literal["cash", "bank_transfer", "stripe"]] = None
    cash_tendered: Optional[Decimal] = Field(None, gt=0, description="With payment_method=cash")
    payments: Optional[list[PaymentLineInput]] = Field(None, min_length=1, max_length=config.MAX_PAYMENT_LINES)

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

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    """The payment side of a business object: what is due, what was paid, and every line."""
    source_type: str
    source_id: str
    order_id: Optional[int] = None            # None until the first payment attempt
    currency: str
    total: Decimal
    state: str                                # unpaid | pending | paid
    method: Optional[str] = None              # cash | bank_transfer | stripe | split
    paid_at: Optional[datetime] = None
    amount_paid: Decimal = Decimal("0")       # sum of completed lines
    balance_due: Decimal = Decimal("0")       # total - amount_paid
    payments: list[PaymentLineResponse] = Field(default_factory=list)


class PayOrderResponse(OrderResponse):
    # Gateway payload (e.g. Stripe client_secret) when the payment is not instant.
    gateway: Optional[dict[str, Any]] = None
