from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class HydroActuatorBase(BaseModel):
    name: str = Field(..., example="Pump 1")
    type: str = Field(..., example="pump")  # pump, light, fan, water_pump, etc.
    pin: Optional[str] = Field(None, example="GPIO12")
    port: int
    is_active: Optional[bool] = True
    default_state: Optional[bool] = False
    device_id: int

class HydroActuatorCreate(HydroActuatorBase):
    device_id: int = Field(..., example=1)

class HydroActuatorUpdate(BaseModel):
    name: Optional[str]
    port: Optional[int] = None
    type: Optional[str]
    pin: Optional[str]
    is_active: Optional[bool]
    default_state: Optional[bool] = None

class HydroActuatorOut(HydroActuatorBase):
    id: int
    device_id: int
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {
        "from_attributes": True
    }
