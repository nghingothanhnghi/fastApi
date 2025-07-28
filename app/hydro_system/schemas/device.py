# app/hydro_system/schemas/device.py
from pydantic import BaseModel
from typing import Optional, Dict,Any
from datetime import datetime

class HydroDeviceBase(BaseModel):
    name: str
    device_id: str
    location: Optional[str] = None
    type: Optional[str] = None
    is_active: Optional[bool] = True
    client_id: Optional[str] = None
    thresholds: Optional[Dict[str, Any]] = None

    model_config = {
        "from_attributes": True
    }

class HydroDeviceCreate(HydroDeviceBase):
    user_id: int

class HydroDeviceUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    type: Optional[str] = None
    is_active: Optional[bool] = None
    thresholds: Optional[Dict[str, Any]] = None  # ✅ Updatable

    model_config = {
        "from_attributes": True
    }

class HydroDeviceOut(HydroDeviceBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {
        "from_attributes": True
    }
