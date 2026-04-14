# app/hydro_system/schemas/batch.py
# Pydantic schemas for growth batches in the hydroponic system
from datetime import date
from pydantic import BaseModel
from typing import Optional

class BatchCreate(BaseModel):
    plant_id: int
    current_stage_id: Optional[int] = None
    zone_id: Optional[int] = None
    start_date: date


class BatchOut(BaseModel):
    id: int
    plant_id: int
    current_stage_id: Optional[int]
    zone_id: Optional[int]
    start_date: date
    status: str

    model_config = {
        "from_attributes": True
    }

class BatchUpdate(BaseModel):
    plant_id: Optional[int] = None
    current_stage_id: Optional[int] = None
    zone_id: Optional[int] = None
    start_date: Optional[date] = None
    status: Optional[str] = None

class BatchDetail(BatchOut):
    plant_name: Optional[str] = None
    current_stage_name: Optional[str] = None
    days_growing: Optional[int] = None

    device_name: Optional[str] = None
    device_location: Optional[str] = None

# Alias for UI clarity if needed
class GrowthBatch(BatchDetail):
    pass
