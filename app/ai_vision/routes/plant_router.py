# app/ai_vision/routes/plant_router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.ai_vision.services.plant_service import plant_service
from app.ai_vision.schemas.plant_schema import PlantCreate, PlantUpdate, PlantOut, CameraCreate, CameraOut

router = APIRouter(prefix="/api/v1/plants", tags=["AI Vision - Plants"])


@router.post("", response_model=PlantOut)
def create_plant(data: PlantCreate, db: Session = Depends(get_db)):
    return plant_service.create_plant(db, **data.model_dump())


@router.get("", response_model=List[PlantOut])
def list_plants(status: Optional[str] = None, db: Session = Depends(get_db)):
    return plant_service.get_all_plants(db, status)


@router.get("/{plant_id}", response_model=PlantOut)
def get_plant(plant_id: int, db: Session = Depends(get_db)):
    plant = plant_service.get_plant(db, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    return plant


@router.patch("/{plant_id}", response_model=PlantOut)
def update_plant(plant_id: int, data: PlantUpdate, db: Session = Depends(get_db)):
    plant = plant_service.update_plant(db, plant_id, data.model_dump(exclude_unset=True))
    if not plant:
        raise HTTPException(404, "Plant not found")
    return plant


camera_router = APIRouter(prefix="/api/v1/cameras", tags=["AI Vision - Cameras"])


@camera_router.post("", response_model=CameraOut)
def create_camera(data: CameraCreate, db: Session = Depends(get_db)):
    return plant_service.create_camera(db, **data.model_dump())


@camera_router.get("", response_model=List[CameraOut])
def list_cameras(db: Session = Depends(get_db)):
    return plant_service.get_all_cameras(db)
