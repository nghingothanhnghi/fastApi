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
from app.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/growth-plans",
    tags=["Growth Plans"],
)


@router.post("/", response_model=GrowthPlanOut)
def create_growth_plan(
    plan_in: GrowthPlanCreate,
    db: Session = Depends(get_db),
):
    return growth_plan_service.create_plan(db, plan_in)


@router.get("/{plan_id}", response_model=GrowthPlanOut)
def get_growth_plan(
    plan_id: int,
    db: Session = Depends(get_db),
):
    plan = growth_plan_service.get_plan(db, plan_id)

    if not plan:
        raise HTTPException(
            status_code=404,
            detail="Growth plan not found",
        )

    return plan


@router.get(
    "/plant/{plant_id}",
    response_model=List[GrowthPlanOut],
)
def get_growth_plans_by_plant(
    plant_id: int,
    db: Session = Depends(get_db),
):
    return growth_plan_service.get_plans_by_plant(db, plant_id)


@router.put("/{plan_id}", response_model=GrowthPlanOut)
def update_growth_plan(
    plan_id: int,
    updates: GrowthPlanUpdate,
    db: Session = Depends(get_db),
):
    plan = growth_plan_service.update_plan(
        db,
        plan_id,
        updates.dict(exclude_unset=True),
    )

    if not plan:
        raise HTTPException(
            status_code=404,
            detail="Growth plan not found",
        )

    return plan


@router.delete("/{plan_id}")
def delete_growth_plan(
    plan_id: int,
    db: Session = Depends(get_db),
):
    deleted = growth_plan_service.delete_plan(db, plan_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Growth plan not found",
        )

    return {"message": "Growth plan deleted successfully"}