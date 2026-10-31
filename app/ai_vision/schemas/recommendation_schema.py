# app/ai_vision/schemas/recommendation_schema.py
from pydantic import BaseModel
from typing import Optional, List, Literal
from datetime import datetime


class AIRecommendationOut(BaseModel):
    id: int
    plant_id: int
    recommendation: str
    reasons: List[str]
    severity: str
    confidence: Optional[float]
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RecommendationStatusUpdate(BaseModel):
    # V1 safety boundary: a reviewer can only acknowledge or dismiss.
    # Never an "executed" state - recommendations do not drive actuators.
    status: Literal["acknowledged", "dismissed"]
