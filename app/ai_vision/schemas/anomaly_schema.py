# app/ai_vision/schemas/anomaly_schema.py
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class PlantAnomalyOut(BaseModel):
    id: int
    plant_id: int
    anomaly_type: str
    severity: str
    description: Optional[str]
    evidence: Optional[Dict[str, Any]]
    detected_at: datetime
    is_resolved: bool

    model_config = {"from_attributes": True}
