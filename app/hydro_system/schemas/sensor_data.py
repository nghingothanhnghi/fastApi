from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class SensorDataSchema(BaseModel):
    id: int
    temperature: Optional[float]
    humidity: Optional[float]
    light: Optional[float]
    moisture: Optional[float]
    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class SensorDataCreateSchema(BaseModel):
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    light: Optional[float] = None
    moisture: Optional[float] = None