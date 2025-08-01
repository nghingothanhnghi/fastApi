# app/hydro_system/schemas/device.py
from pydantic import BaseModel
from typing import Optional, Dict,Any
from datetime import datetime

class HydroDeviceBase(BaseModel):
    name: str
    device_id: str
    external_id: Optional[str] = None
    location: Optional[str] = None
    type: Optional[str] = None
    is_active: Optional[bool] = True
    thresholds: Optional[Dict[str, Any]] = None

    model_config = {
        "from_attributes": True
    }

class HydroDeviceCreate(HydroDeviceBase):
    client_id: Optional[str] = None
    user_id: Optional[int] = None

class HydroDeviceUpdate(BaseModel):
    name: Optional[str] = None
    external_id: Optional[str] = None
    user_id: Optional[int] = None
    client_id: Optional[str] = None
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
