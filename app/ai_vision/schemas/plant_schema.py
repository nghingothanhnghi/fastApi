# app/ai_vision/schemas/plant_schema.py
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class CameraCreate(BaseModel):
    name: str
    camera_type: str = "ip_camera"
    stream_url: Optional[str] = None
    location: Optional[str] = None
    hydro_device_id: Optional[int] = None


class CameraOut(CameraCreate):
    id: int
    is_active: bool
    client_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PlantCreate(BaseModel):
    species: str
    variety: Optional[str] = None
    location: Optional[str] = None
    growing_system: Optional[str] = None
    planted_at: Optional[datetime] = None
    camera_id: Optional[int] = None
    hydro_plant_id: Optional[int] = None
    hydro_batch_id: Optional[int] = None
    expected_growth_profile: Optional[Dict[str, Any]] = None


class PlantUpdate(BaseModel):
    status: Optional[str] = None
    camera_id: Optional[int] = None
    expected_growth_profile: Optional[Dict[str, Any]] = None


class PlantOut(PlantCreate):
    id: int
    status: str
    client_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
