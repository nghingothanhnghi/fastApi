# app/ai_vision/schemas/image_schema.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class PlantImageOut(BaseModel):
    id: int
    plant_id: int
    camera_id: Optional[int]
    public_url: Optional[str]
    annotated_url: Optional[str] = None
    width: Optional[int]
    height: Optional[int]
    processing_status: str
    captured_at: datetime

    model_config = {"from_attributes": True}


class InferenceJobOut(BaseModel):
    id: int
    image_id: int
    model_name: str
    model_version: str
    status: str
    error_message: Optional[str] = None
    queued_at: datetime
    completed_at: Optional[datetime] = None

    # NEW — pulled from the related PlantImage so the frontend
    # never has to make a second call to /vision/images/{id}
    public_url: Optional[str] = None
    annotated_url: Optional[str] = None

    model_config = {"from_attributes": True}
