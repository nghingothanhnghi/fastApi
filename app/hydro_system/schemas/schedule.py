from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, time

class HydroScheduleBase(BaseModel):
    actuator_id: int
    start_time: time = Field(..., json_schema_extra={"example": "08:00:00"})
    end_time: time = Field(..., json_schema_extra={"example": "20:00:00"})
    repeat_days: str = Field("mon,tue,wed,thu,fri,sat,sun", json_schema_extra={"example": "mon,tue,wed,thu,fri,sat,sun"})
    is_active: bool = True

class HydroScheduleCreate(HydroScheduleBase):
    pass

class HydroScheduleUpdate(BaseModel):
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    repeat_days: Optional[str] = None
    is_active: Optional[bool] = None

class HydroScheduleOut(HydroScheduleBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {
        "from_attributes": True
    }
