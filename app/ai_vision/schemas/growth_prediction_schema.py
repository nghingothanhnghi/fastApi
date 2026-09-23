# app/ai_vision/schemas/growth_prediction_schema.py
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class PlantGrowthPredictionOut(BaseModel):
    id: int
    plant_id: int
    growth_record_id: Optional[int] = None

    horizon_days: int
    target_date: datetime

    basis_growth_rate_pct_per_day: Optional[float] = None
    basis_sample_count: int
    basis_variance: Optional[float] = None

    predicted_canopy_area_px: Optional[float] = None
    predicted_growth_pct: Optional[float] = None
    confidence: Optional[float] = None

    current_stage_id: Optional[int] = None
    current_stage_name: Optional[str] = None
    scheduled_stage_transition_date: Optional[datetime] = None
    projected_stage_transition_date: Optional[datetime] = None
    stage_transition_delta_days: Optional[float] = None

    reasons: List[str]
    created_at: datetime

    model_config = {"from_attributes": True}