# app/billiard/schemas/table.py
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.billiard.models.table import TableStatus


class TableCreate(BaseModel):
    name: str
    hourly_rate: Decimal


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

    session_id: int | None = None

    start_time: str | None = None
    elapsed_minutes: int | None = None

    current_table_fee: Decimal | None = None
    current_product_fee: Decimal | None = None
    current_total: Decimal | None = None