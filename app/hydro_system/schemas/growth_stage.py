# app/hydro_system/schemas/growth_stage.py
# Pydantic schemas for growth stages in the hydroponic system
# from pydantic import BaseModel
# from typing import Optional, List
# from .growth_recipe import GrowthRecipeOut, GrowthRecipeInput

# class GrowthStageBase(BaseModel):
#     name: str
#     day_start: int
#     day_end: int

# class GrowthStageCreate(GrowthStageBase):
#     plant_id: int

# class GrowthStageUpdate(GrowthStageBase):
#     pass

# # 🔥 NEW — for update with recipes
# class GrowthStageWithRecipesUpdate(GrowthStageBase):
#     recipes: List[GrowthRecipeInput]

# class GrowthStageOut(GrowthStageBase):
#     id: int
#     plant_id: int
#     recipes: List[GrowthRecipeOut] = []

#     model_config = {
#         "from_attributes": True
#     }

from pydantic import BaseModel
from typing import Optional, List
from .growth_recipe import GrowthRecipeOut, GrowthRecipeInput

class GrowthStageBase(BaseModel):
    name: str
    day_start: int
    day_end: int

class GrowthStageCreate(GrowthStageBase):
    # ✅ plan_id replaces plant_id as the required parent — plant_id is
    # derived server-side from the plan (see growth_stage_service.create_stage)
    # so a stage always lands under the correct plant automatically and can
    # never be attached to the wrong plan/plant pairing.
    plan_id: int

class GrowthStageUpdate(GrowthStageBase):
    pass

# 🔥 NEW — for update with recipes
class GrowthStageWithRecipesUpdate(GrowthStageBase):
    recipes: List[GrowthRecipeInput]

class GrowthStageOut(GrowthStageBase):
    id: int
    plant_id: int
    plan_id: Optional[int] = None
    recipes: List[GrowthRecipeOut] = []

    model_config = {
        "from_attributes": True
    }
