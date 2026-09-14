# app/ai_vision/schemas/health_schema.py
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class PlantHealthOut(BaseModel):
    plant_id: int
    health_score: int
    status: str
    visual_indicators: List[str] = []
    possible_issues: List[Dict[str, Any]] = []
    sensor_snapshot: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
