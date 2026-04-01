from pydantic import BaseModel
from typing import Optional, List
from .growth_recipe import GrowthRecipeOut

class GrowthStageBase(BaseModel):
    name: str
    day_start: int
    day_end: int

class GrowthStageCreate(GrowthStageBase):
    plant_id: int

class GrowthStageOut(GrowthStageBase):
    id: int
    plant_id: int
    recipes: List[GrowthRecipeOut] = []

    model_config = {
        "from_attributes": True
    }
