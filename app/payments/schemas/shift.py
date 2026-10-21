# app/payments/schemas/shift.py
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field


class OpenShiftRequest(BaseModel):
    opening_float: Decimal = Field(Decimal("0"), ge=0, description="Cash already in the drawer")
    note: Optional[str] = Field(None, max_length=255)


class CashMovementRequest(BaseModel):
    type: Literal["pay_in", "pay_out"]
    amount: Decimal = Field(..., gt=0)
    reason: str = Field(..., min_length=3, max_length=255)


class CloseShiftRequest(BaseModel):
    counted_cash: Decimal = Field(..., ge=0, description="Cash actually counted in the drawer")
    note: Optional[str] = Field(None, max_length=255)


class CashMovementResponse(BaseModel):
    id: int
    type: str
    amount: Decimal
    reason: str
    created_by: Optional[str] = None
    created_at: datetime


class MethodTotals(BaseModel):
    method: str
    received_count: int
    received_total: Decimal
    voided_total: Decimal
    net_total: Decimal


class ShiftResponse(BaseModel):
    id: int
    status: str
    opened_at: datetime
    closed_at: Optional[datetime] = None
    opening_float: Decimal
    expected_cash: Optional[Decimal] = None    # frozen at close; live value is in ShiftSummary
    counted_cash: Optional[Decimal] = None
    variance: Optional[Decimal] = None         # counted - expected (negative = cash missing)
    note: Optional[str] = None
    close_note: Optional[str] = None
    opened_by: Optional[str] = None
    closed_by: Optional[str] = None


class ShiftSummary(ShiftResponse):
    """Drawer maths for the shift window: expected = float + cash sales - cash voids + pay-ins - pay-outs."""
    cash_sales: Decimal
    cash_voids: Decimal
    pay_ins: Decimal
    pay_outs: Decimal
    change_given: Decimal                      # informational: already netted out of cash_sales
    payments_count: int
    methods: list[MethodTotals]
    movements: list[CashMovementResponse]
