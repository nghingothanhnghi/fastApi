from pydantic import BaseModel, Field, model_validator
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
    rain_detected: Optional[bool] = Field(None, description="True if rain sensor detects rain")
    rain_intensity: Optional[float] = Field(None, ge=0)

    # ✅ NEW — fields your ESP32 actually sends; previously dropped silently
    # because they weren't declared (Pydantic ignores unknown fields by
    # default). rain_level_pct feeds rain_intensity if rain_intensity
    # isn't sent directly; rain_raw is kept for calibration only.
    rain_level_pct: Optional[float] = Field(None, ge=0, le=100)
    rain_raw: Optional[int] = Field(None)

    @model_validator(mode="after")
    def _derive_rain_intensity(self):
        if self.rain_intensity is None and self.rain_level_pct is not None:
            self.rain_intensity = self.rain_level_pct
        return self

class SensorDataSchema(BaseModel):
    id: int
    temperature: Optional[float] = Field(None, description="Temperature in Celsius")
    humidity: Optional[float] = Field(None, description="Humidity percentage (0-100%)")
    light: Optional[float] = Field(None, description="Light intensity in lux")
    moisture: Optional[float] = Field(None, description="Soil moisture percentage (0-100%)")
    water_level: Optional[float] = Field(None, description="Water level percentage (0-100%)")
    ec: Optional[float] = Field(None, description="Electrical Conductivity (mS/cm)")
    ppm: Optional[float] = Field(None, description="Parts Per Million")
    rain_detected: Optional[bool] = Field(None, description="True if rain sensor detects rain")
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
    