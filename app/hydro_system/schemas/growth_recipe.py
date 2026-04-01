from pydantic import BaseModel
from typing import Optional
from datetime import time

class GrowthRecipeBase(BaseModel):
    actuator_type: str
    action: str
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    interval_on_min: Optional[int] = None
    interval_off_min: Optional[int] = None

class GrowthRecipeCreate(GrowthRecipeBase):
    stage_id: int

class GrowthRecipeOut(GrowthRecipeBase):
    id: int
    stage_id: int

    model_config = {
        "from_attributes": True
    }
