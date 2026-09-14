# app/ai_vision/schemas/growth_schema.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class PlantGrowthOut(BaseModel):
    plant_id: int
    canopy_area_px: Optional[float]
    growth_pct_since_last: Optional[float]
    growth_rate_pct_per_day: Optional[float]
    baseline_growth_rate_pct_per_day: Optional[float]
    deviation_from_baseline_pct: Optional[float]
    created_at: datetime

    model_config = {"from_attributes": True}
