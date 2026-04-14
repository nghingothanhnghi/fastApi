# app/hydro_system/schemas/growth_recipe.py
# Pydantic schemas for growth recipes in the hydroponic system
from pydantic import BaseModel, model_validator
from typing import Optional, Literal
from datetime import time

class GrowthRecipeBase(BaseModel):
    actuator_type: str
    action: Literal["on", "interval"]
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    interval_on_min: Optional[int] = None
    interval_off_min: Optional[int] = None

    @model_validator(mode="after")
    def validate_action_fields(self):
        if self.action == "on":
            if not self.start_time or not self.end_time:
                raise ValueError("start_time and end_time required for 'on'")
        elif self.action == "interval":
            if not self.interval_on_min or not self.interval_off_min:
                raise ValueError("interval values required for 'interval'")
        return self    

# 🔹 For nested input (NO stage_id)
class GrowthRecipeInput(GrowthRecipeBase):
    pass

class GrowthRecipeCreate(GrowthRecipeBase):
    stage_id: int

class GrowthRecipeUpdate(BaseModel):
    actuator_type: Optional[str] = None
    action: Optional[Literal["on", "interval"]] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    interval_on_min: Optional[int] = None
    interval_off_min: Optional[int] = None

class GrowthRecipeOut(GrowthRecipeBase):
    id: int
    stage_id: int

    model_config = {
        "from_attributes": True
    }
