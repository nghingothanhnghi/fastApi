# app/billiard/schemas/table.py
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.billiard.models.table import TableStatus


class TableCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    hourly_rate: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)


class TableUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    hourly_rate: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=2,
    )    


class TableResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    status: TableStatus
    hourly_rate: Decimal


class ActiveTableResponse(BaseModel):
    id: int
    name: str
    status: TableStatus
    session_id: int
    start_time: datetime
    elapsed_minutes: int
    hourly_rate: Decimal
    current_table_fee: Decimal
    current_product_fee: Decimal
    ends_at: Optional[datetime] = None          # timed play: when the planned time is up
    remaining_seconds: Optional[int] = None     # negative once past ends_at; None for open play
    is_overtime: bool = False                   # flag only: the server never stops a session by itself
    package_name: Optional[str] = None          # session started with a package
    overtime_minutes: Optional[int] = None      # minutes beyond the package so far; None without a package
    current_discount: Decimal = Decimal("0")
    current_total: Decimal                      # table fee + products - discount