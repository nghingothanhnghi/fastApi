from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Union

class SensorPayloadSchema(BaseModel):
    temperature: Optional[float] = Field(None, description="Temperature in Celsius", ge=-50, le=100)
    humidity: Optional[float] = Field(None, description="Humidity percentage (0-100%)", ge=0, le=100)
    light: Optional[float] = Field(None, description="Light intensity in lux", ge=0)
    moisture: Optional[float] = Field(None, description="Soil moisture percentage (0-100%)", ge=0, le=100)
    water_level: Optional[float] = Field(None, description="Water level percentage (0-100%)", ge=0, le=100)
    ec: Optional[float] = Field(None, description="Electrical Conductivity (mS/cm)", ge=0)
    ppm: Optional[float] = Field(None, description="Parts Per Million", ge=0)

class SensorDataSchema(BaseModel):
    id: int
    temperature: Optional[float] = Field(None, description="Temperature in Celsius")
    humidity: Optional[float] = Field(None, description="Humidity percentage (0-100%)")
    light: Optional[float] = Field(None, description="Light intensity in lux")
    moisture: Optional[float] = Field(None, description="Soil moisture percentage (0-100%)")
    water_level: Optional[float] = Field(None, description="Water level percentage (0-100%)")
    ec: Optional[float] = Field(None, description="Electrical Conductivity (mS/cm)")
    ppm: Optional[float] = Field(None, description="Parts Per Million")
    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class SensorDataCreateSchema(BaseModel):
    device_id: Union[int, str] = Field(
        ..., description="Device identifier (can be numeric DB ID or external string ID)"
    )

    client_id: Optional[str] = None
    data: SensorPayloadSchema
    