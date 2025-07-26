# app/hydro_system/schemas/device.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class DeviceBase(BaseModel):
    name: str
    device_id: str
    location: Optional[str] = None
    type: Optional[str] = None
    is_active: Optional[bool] = True
    client_id: Optional[str] = None

    model_config = {
        "from_attributes": True
    }

class DeviceCreate(DeviceBase):
    user_id: int

class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    type: Optional[str] = None
    is_active: Optional[bool] = None

    model_config = {
        "from_attributes": True
    }

class DeviceOut(DeviceBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {
        "from_attributes": True
    }
