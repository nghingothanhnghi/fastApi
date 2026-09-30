# app/hydro_system/routes/batch_router.py
# Routes for managing plant batches, growth stages, and growth recipes in the hydroponic system
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.hydro_system.schemas.batch import BatchCreate, BatchUpdate, BatchDetail
from app.hydro_system.schemas.plant import PlantCreate, PlantOut
from app.hydro_system.schemas.growth_stage import GrowthStageCreate, GrowthStageOut, GrowthStageWithRecipesUpdate, GrowthStageUpdate
from app.hydro_system.schemas.growth_recipe import GrowthRecipeCreate, GrowthRecipeOut, GrowthRecipeUpdate
from app.hydro_system.services.plant_batch_service import plant_batch_service
from app.hydro_system.services.plant_service import plant_service

from app.hydro_system.services.growth_stage_service import (
    growth_stage_service,
    StageRangeError,
    StageInUseError,
)
from app.hydro_system.services.growth_recipe_service import growth_recipe_service
from app.hydro_system.services.recipe_engine_service import recipe_engine_service
from app.hydro_system.helpers.schedule_helper import get_local_today

router = APIRouter(prefix="/batches", tags=["Plant Batches"])

# Plant Metadata Routes
@router.post("/plants", response_model=PlantOut, tags=["Plants"])
def create_plant(plant_in: PlantCreate, db: Session = Depends(get_db)):
    return plant_service.create_plant(db, plant_in)

@router.get("/plants", response_model=List[PlantOut], tags=["Plants"])
def get_plants(db: Session = Depends(get_db)):
    return plant_service.get_all_plants(db)

# Batch Routes
@router.post("", response_model=BatchDetail)
def create_batch(batch_in: BatchCreate, db: Session = Depends(get_db)):
    try:
        batch = plant_batch_service.create_batch(db, batch_in)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return plant_batch_service.get_batch_detail(db, batch.id)

@router.get("", response_model=List[BatchDetail])
def get_batches(db: Session = Depends(get_db)):
    return plant_batch_service.get_all_batches_detail(db)

@router.get("/{batch_id}", response_model=BatchDetail)
def get_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = plant_batch_service.get_batch_detail(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch

@router.put("/{batch_id}", response_model=BatchDetail)
def update_batch(batch_id: int, batch_in: BatchUpdate, db: Session = Depends(get_db)):
    # BatchUpdate (all fields optional) — BatchCreate wrongly required
    # plant_id and start_date on every PUT.
    try:
        batch = plant_batch_service.update_batch(
            db,
            batch_id,
            batch_in.dict(exclude_unset=True),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    return plant_batch_service.get_batch_detail(db, batch.id)

@router.delete("/{batch_id}", status_code=204)
def delete_batch(batch_id: int, db: Session = Depends(get_db)):
    success = plant_batch_service.delete_batch(db, batch_id)

    if not success:
        raise HTTPException(status_code=404, detail="Batch not found")

    return None

@router.post("/{batch_id}/set-stage/{stage_id}")
def set_batch_stage(batch_id: int, stage_id: int, db: Session = Depends(get_db)):
    batch = plant_batch_service.get_batch(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    stage = growth_stage_service.get_stage(db, stage_id)
    if not stage:
        raise HTTPException(status_code=404, detail="Growth stage not found")

    if stage.plan_id != batch.plan_id:
        raise HTTPException(
            status_code=400,
            detail="Stage does not belong to this batch's growth plan",
        )

    try:
        batch.current_stage_id = stage_id

        # Progression is derived from start_date. Without shifting it, the
        # next GET /batches or the 12h job would silently revert this stage.
        batch.start_date = get_local_today() - timedelta(days=stage.day_start)        

        # Deletes old plant_auto schedules and adds the new ones (no commit inside).
        recipe_engine_service.apply_stage_recipes(db, batch, stage.recipes)

        # Single commit: stage change + schedule rewrite land together.
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"message": f"Stage {stage.name} applied to batch {batch_id}"}

# Growth Stage Routes
@router.post("/stages", response_model=GrowthStageOut, tags=["Growth Stages"])
def create_stage(stage_in: GrowthStageCreate, db: Session = Depends(get_db)):
    try:
        return growth_stage_service.create_stage(db, stage_in)
    except LookupError as e:          # unknown plan_id
        raise HTTPException(status_code=404, detail=str(e))
    except StageRangeError as e:      # overlap / bad range
        raise HTTPException(status_code=409, detail=str(e))

@router.get("/stages/plant/{plant_id}", response_model=List[GrowthStageOut], tags=["Growth Stages"])
def get_stages(plant_id: int, db: Session = Depends(get_db)):
    return growth_stage_service.get_stages_by_plant(db, plant_id)

@router.put("/stages/{stage_id}", response_model=GrowthStageOut, tags=["Growth Stages"])
def update_stage(stage_id: int, updates: GrowthStageUpdate, db: Session = Depends(get_db)):
    try:
        stage = growth_stage_service.update_stage(db, stage_id, updates.dict(exclude_unset=True))
    except StageRangeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")

    # Day range may have moved: refresh schedules of batches on this stage
    recipe_engine_service.reapply_for_stage(db, stage_id)
    db.commit()
    db.refresh(stage)
    return stage

@router.put("/stages/{stage_id}/with-recipes", response_model=GrowthStageOut, tags=["Growth Stages"])
def update_stage_with_recipes(
    stage_id: int,
    payload: GrowthStageWithRecipesUpdate,
    db: Session = Depends(get_db)
):
    try:
        stage = growth_stage_service.update_stage_with_recipes(db, stage_id, payload)
    except StageRangeError as e:
        raise HTTPException(status_code=409, detail=str(e))

    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")

    # Recipes were replaced: refresh schedules of batches running this stage
    recipe_engine_service.reapply_for_stage(db, stage_id)
    db.commit()
    db.refresh(stage)
    return stage

@router.delete("/stages/{stage_id}", tags=["Growth Stages"])
def delete_stage(stage_id: int, db: Session = Depends(get_db)):
    try:
        success = growth_stage_service.delete_stage(db, stage_id)
    except StageInUseError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not success:
        raise HTTPException(status_code=404, detail="Stage not found")
    return {"message": "Stage deleted"}

# Growth Recipe Routes
@router.post("/recipes", response_model=GrowthRecipeOut, tags=["Growth Recipes"])
def create_recipe(recipe_in: GrowthRecipeCreate, db: Session = Depends(get_db)):
    recipe = growth_recipe_service.create_recipe(db, recipe_in)
    recipe_engine_service.reapply_for_stage(db, recipe.stage_id)
    db.commit()
    db.refresh(recipe)
    return recipe

@router.put("/recipes/{recipe_id}", response_model=GrowthRecipeOut, tags=["Growth Recipes"])
def update_recipe(recipe_id: int, updates: GrowthRecipeUpdate, db: Session = Depends(get_db)):
    recipe = growth_recipe_service.update_recipe(
        db,
        recipe_id,
        updates.dict(exclude_unset=True)
    )
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    recipe_engine_service.reapply_for_stage(db, recipe.stage_id)
    db.commit()
    db.refresh(recipe)
    return recipe


@router.delete("/recipes/{recipe_id}", tags=["Growth Recipes"])
def delete_recipe(recipe_id: int, db: Session = Depends(get_db)):
    recipe = growth_recipe_service.get_recipe(db, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    stage_id = recipe.stage_id  # capture BEFORE the row is deleted
    growth_recipe_service.delete_recipe(db, recipe_id)

    recipe_engine_service.reapply_for_stage(db, stage_id)
    db.commit()
    return {"message": "Recipe deleted"}
