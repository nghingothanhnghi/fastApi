# app/billiard/schemas/table.py
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.billiard.models.table import TableStatus


class TableCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    hourly_rate: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)


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
    current_total: Decimal