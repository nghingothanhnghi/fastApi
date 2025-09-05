from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

class HydroActuatorBase(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "Pump 1"})
    type: str = Field(..., json_schema_extra={"example": "pump"})  # pump, light, fan, water_pump, etc.
    pin: Optional[str] = Field(None, json_schema_extra={"example": "PIN031"})
    port: int
    is_active: Optional[bool] = True
    default_state: Optional[bool] = False
    device_id: int
    sensor_key: Optional[str] = Field(
        None,
        json_schema_extra={"example": "temperature"},
        description="The sensor key this actuator is linked to (e.g., temperature, humidity)"
    )    

class HydroActuatorCreate(HydroActuatorBase):
    device_id: int = Field(..., json_schema_extra={"example": 1})

class HydroActuatorUpdate(BaseModel):
    name: Optional[str] = None
    port: Optional[int] = None
    type: Optional[str] = None
    pin: Optional[str] = None
    is_active: Optional[bool] = None
    default_state: Optional[bool] = None
    sensor_key: Optional[str] = Field(
        None,
        json_schema_extra={"example": "humidity"},
        description="Update the linked sensor key"
    )    
class HydroActuatorOut(HydroActuatorBase):
    id: int
    device_id: int
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {
        "from_attributes": True
    }
