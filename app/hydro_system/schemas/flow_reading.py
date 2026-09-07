# app/hydro_system/schemas/flow_reading.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Union


class FlowReadingCreate(BaseModel):
    # accept either the actuator's DB id, or (device external id + pin/port)
    # depending on what the hardware reports — keep it simple: require actuator_id.
    actuator_id: int
    flow_rate: float = Field(..., ge=0, description="Flow rate in liters per minute (L/min)")


class FlowReadingOut(BaseModel):
    id: int
    actuator_id: int
    device_id: int
    flow_rate: float
    created_at: datetime

    model_config = {
        "from_attributes": True
    }