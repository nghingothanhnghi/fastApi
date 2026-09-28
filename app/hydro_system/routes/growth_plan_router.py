# app/hydro_system/routes/growth_plan.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.hydro_system.schemas.growth_plan import (
    GrowthPlanCreate,
    GrowthPlanOut,
    GrowthPlanUpdate,
)
from app.hydro_system.services.growth_plan_service import growth_plan_service
from app.hydro_system.services.growth_stage_service import growth_stage_service
from app.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/growth-plans",
    tags=["Growth Plans"],
)


@router.post("/", response_model=GrowthPlanOut)
def create_growth_plan(plan_in: GrowthPlanCreate, db: Session = Depends(get_db)):
    """The first plan for a plant automatically becomes its default."""
    try:
        return growth_plan_service.create_plan(db, plan_in)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


# NOTE: declared before "/{plan_id}" routes; the two-segment paths below
# can't collide with the single-segment "/{plan_id}" anyway.
@router.get("/plant/{plant_id}", response_model=List[GrowthPlanOut])
def get_growth_plans_by_plant(plant_id: int, db: Session = Depends(get_db)):
    return growth_plan_service.get_plans_by_plant(db, plant_id)


@router.get("/{plan_id}", response_model=GrowthPlanOut)
def get_growth_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = growth_plan_service.get_plan(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Growth plan not found")
    return plan


@router.get("/{plan_id}/stages", response_model=GrowthPlanWithStages)
def get_growth_plan_with_stages(plan_id: int, db: Session = Depends(get_db)):
    """The plan plus its stages (ordered by day_start) and each stage's recipes."""
    plan = growth_plan_service.get_plan(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Growth plan not found")

    stages = growth_stage_service.get_stages_by_plan(db, plan_id)
    return GrowthPlanWithStages(
        **GrowthPlanOut.model_validate(plan).model_dump(),
        stages=[GrowthStageOut.model_validate(s) for s in stages],
    )


@router.put("/{plan_id}", response_model=GrowthPlanOut)
def update_growth_plan(plan_id: int, updates: GrowthPlanUpdate, db: Session = Depends(get_db)):
    try:
        plan = growth_plan_service.update_plan(db, plan_id, updates.dict(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not plan:
        raise HTTPException(status_code=404, detail="Growth plan not found")
    return plan


@router.delete("/{plan_id}")
def delete_growth_plan(plan_id: int, db: Session = Depends(get_db)):
    try:
        deleted = growth_plan_service.delete_plan(db, plan_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Growth plan not found")
    return {"message": "Growth plan deleted successfully"}