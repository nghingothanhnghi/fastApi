# app/hydro_system/schemas/growth_plan.py
# Pydantic schemas for growth plans (named cultivation strategies per plant)
from pydantic import BaseModel
from typing import Optional, List
from .growth_stage import GrowthStageOut


class GrowthPlanBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_default: Optional[bool] = False


class GrowthPlanCreate(GrowthPlanBase):
    plant_id: int


class GrowthPlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_default: Optional[bool] = None


class GrowthPlanOut(GrowthPlanBase):
    id: int
    plant_id: int

    model_config = {
        "from_attributes": True
    }


# 🔥 With nested stages (and their recipes), for a single-call plan view
class GrowthPlanWithStages(GrowthPlanOut):
    stages: List[GrowthStageOut] = []

    model_config = {
        "from_attributes": True
    }