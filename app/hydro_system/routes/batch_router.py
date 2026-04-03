from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.hydro_system.schemas.batch import BatchCreate, BatchOut
from app.hydro_system.schemas.growth_stage import GrowthStageCreate, GrowthStageOut
from app.hydro_system.schemas.growth_recipe import GrowthRecipeCreate, GrowthRecipeOut
from app.hydro_system.services.plant_batch_service import plant_batch_service
from app.hydro_system.services.growth_stage_service import growth_stage_service
from app.hydro_system.services.growth_recipe_service import growth_recipe_service
from app.hydro_system.controllers.recipe_engine_controller import recipe_engine_controller

router = APIRouter(prefix="/batches", tags=["Plant Batches"])

@router.post("", response_model=BatchOut, status_code=status.HTTP_201_CREATED)
def create_batch(batch_in: BatchCreate, db: Session = Depends(get_db)):
    return plant_batch_service.create_batch(db, batch_in)

@router.get("", response_model=List[BatchOut])
def get_batches(db: Session = Depends(get_db)):
    return plant_batch_service.get_all_batches(db)

@router.get("/{batch_id}", response_model=BatchOut)
def get_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = plant_batch_service.get_batch(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch

@router.post("/{batch_id}/set-stage/{stage_id}")
def set_batch_stage(batch_id: int, stage_id: int, db: Session = Depends(get_db)):
    batch = plant_batch_service.get_batch(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    stage = growth_stage_service.get_stage(db, stage_id)
    if not stage:
        raise HTTPException(status_code=404, detail="Growth stage not found")
    
    # Update batch current stage
    plant_batch_service.update_batch(db, batch_id, {"current_stage_id": stage_id})
    
    # Apply all recipes for this stage
    for recipe in stage.recipes:
        recipe_engine_controller.apply_stage_recipe(db, batch, recipe)
        
    return {"message": f"Stage {stage.name} applied to batch {batch_id}"}

# Growth Stage Routes
@router.post("/stages", response_model=GrowthStageOut, tags=["Growth Stages"])
def create_stage(stage_in: GrowthStageCreate, db: Session = Depends(get_db)):
    return growth_stage_service.create_stage(db, stage_in)

@router.get("/stages/plant/{plant_id}", response_model=List[GrowthStageOut], tags=["Growth Stages"])
def get_stages(plant_id: int, db: Session = Depends(get_db)):
    return growth_stage_service.get_stages_by_plant(db, plant_id)

# Growth Recipe Routes
@router.post("/recipes", response_model=GrowthRecipeOut, tags=["Growth Recipes"])
def create_recipe(recipe_in: GrowthRecipeCreate, db: Session = Depends(get_db)):
    return growth_recipe_service.create_recipe(db, recipe_in)
