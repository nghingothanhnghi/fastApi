# app/billiard/schemas/report.py
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class TableUsageRow(BaseModel):
    table_id: int
    table_name: str
    times_played: int
    total_minutes: int
    table_revenue: Decimal      # paid sessions only
    product_revenue: Decimal    # paid sessions only
    total_revenue: Decimal      # paid sessions only
    unpaid_total: Decimal       # stopped but not yet paid


class TableUsageReport(BaseModel):
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    rows: list[TableUsageRow]
    totals: TableUsageRow