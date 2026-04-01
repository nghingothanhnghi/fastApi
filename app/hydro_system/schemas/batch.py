# app/hydro_system/schemas/batch.py
from datetime import date
from pydantic import BaseModel

class BatchCreate(BaseModel):
    plant_id: int
    current_stage_id: int | None = None
    zone_id: int | None = None
    start_date: date


class BatchOut(BaseModel):
    id: int
    plant_id: int
    current_stage_id: int | None
    zone_id: int | None
    start_date: date
    status: str

    model_config = {
        "from_attributes": True
    }