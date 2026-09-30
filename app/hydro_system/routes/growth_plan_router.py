# app/hydro_system/routes/growth_plan_router.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.hydro_system.schemas.growth_plan import (
    GrowthPlanCreate,
    GrowthPlanDuplicate,
    GrowthPlanOut,
    GrowthPlanUpdate,
    GrowthPlanWithStages,
)
from app.hydro_system.schemas.growth_stage import GrowthStageOut
from app.hydro_system.services.growth_plan_service import (
    growth_plan_service,
    PlanNameConflictError,
)
from app.hydro_system.services.growth_stage_service import growth_stage_service
from app.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/growth-plans",
    tags=["Growth Plans"],
)


def _out(plan, counts: dict) -> GrowthPlanOut:
    """Serialize a plan with its batch_count filled in."""
    out = GrowthPlanOut.model_validate(plan)
    out.batch_count = counts.get(plan.id, 0)
    return out


def _out_single(db: Session, plan) -> GrowthPlanOut:
    return _out(plan, growth_plan_service.get_batch_counts(db, [plan.id]))


@router.post("/", response_model=GrowthPlanOut)
def create_growth_plan(plan_in: GrowthPlanCreate, db: Session = Depends(get_db)):
    """The first plan for a plant automatically becomes its default."""
    try:
        plan = growth_plan_service.create_plan(db, plan_in)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PlanNameConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _out_single(db, plan)


# Declared before "/{plan_id}" routes; two-segment paths can't collide anyway.
@router.get("/plant/{plant_id}", response_model=List[GrowthPlanOut])
def get_growth_plans_by_plant(plant_id: int, db: Session = Depends(get_db)):
    plans = growth_plan_service.get_plans_by_plant(db, plant_id)
    counts = growth_plan_service.get_batch_counts(db, [p.id for p in plans])
    return [_out(p, counts) for p in plans]


@router.get("/{plan_id}", response_model=GrowthPlanOut)
def get_growth_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = growth_plan_service.get_plan(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Growth plan not found")
    return _out_single(db, plan)


@router.get("/{plan_id}/stages", response_model=GrowthPlanWithStages)
def get_growth_plan_with_stages(plan_id: int, db: Session = Depends(get_db)):
    """The plan plus its stages (ordered by day_start) and each stage's recipes."""
    plan = growth_plan_service.get_plan(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Growth plan not found")

    stages = growth_stage_service.get_stages_by_plan(db, plan_id)
    base = _out_single(db, plan).model_dump()
    return GrowthPlanWithStages(
        **base,
        stages=[GrowthStageOut.model_validate(s) for s in stages],
    )


@router.get("/{plan_id}/validation")
def validate_growth_plan(plan_id: int, db: Session = Depends(get_db)):
    """
    Report-only: day gaps between stages (warnings) and overlaps (legacy data
    only, new overlaps are rejected on write). Use it to show a warning banner
    in the plan editor.
    """
    if not growth_plan_service.get_plan(db, plan_id):
        raise HTTPException(status_code=404, detail="Growth plan not found")
    return growth_stage_service.get_plan_issues(db, plan_id)


@router.post("/{plan_id}/duplicate", response_model=GrowthPlanOut, status_code=201)
def duplicate_growth_plan(
    plan_id: int,
    body: GrowthPlanDuplicate = GrowthPlanDuplicate(),
    db: Session = Depends(get_db),
):
    """Deep-copies the plan with all its stages and recipes. The copy is never the default."""
    try:
        plan = growth_plan_service.duplicate_plan(db, plan_id, body.name)
    except PlanNameConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not plan:
        raise HTTPException(status_code=404, detail="Growth plan not found")
    return _out_single(db, plan)


@router.put("/{plan_id}", response_model=GrowthPlanOut)
def update_growth_plan(plan_id: int, updates: GrowthPlanUpdate, db: Session = Depends(get_db)):
    try:
        plan = growth_plan_service.update_plan(db, plan_id, updates.dict(exclude_unset=True))
    except PlanNameConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not plan:
        raise HTTPException(status_code=404, detail="Growth plan not found")
    return _out_single(db, plan)


@router.delete("/{plan_id}")
def delete_growth_plan(plan_id: int, db: Session = Depends(get_db)):
    try:
        deleted = growth_plan_service.delete_plan(db, plan_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Growth plan not found")
    return {"message": "Growth plan deleted successfully"}