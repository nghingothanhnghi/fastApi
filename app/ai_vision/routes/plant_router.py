# app/ai_vision/routes/plant_router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.user.utils.token import get_current_user
from app.user.models.user import User
from app.ai_vision.services.plant_service import plant_service
from app.ai_vision.helpers.access_helper import ensure_plant_access, ensure_camera_access
from app.ai_vision.schemas.plant_schema import PlantCreate, PlantUpdate, PlantOut, CameraCreate, CameraOut

router = APIRouter(prefix="/api/v1/plants", tags=["AI Vision - Plants"])


@router.post("", response_model=PlantOut)
def create_plant(
    data: PlantCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return plant_service.create_plant(db, **data.model_dump(), client_id=current_user.client_id)


@router.get("", response_model=List[PlantOut])
def list_plants(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.is_super_admin():
        return plant_service.get_all_plants(db, status)
    return plant_service.get_all_plants_by_client(db, current_user.client_id, status)


@router.get("/{plant_id}", response_model=PlantOut)
def get_plant(
    plant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plant = plant_service.get_plant(db, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    ensure_plant_access(plant, current_user)
    return plant

@router.patch("/{plant_id}", response_model=PlantOut)
def update_plant(
    plant_id: int,
    data: PlantUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plant = plant_service.get_plant(db, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    ensure_plant_access(plant, current_user)
    return plant_service.update_plant(db, plant_id, data.model_dump(exclude_unset=True))

@router.get("/by-hydro-batch/{hydro_batch_id}", response_model=PlantOut)
def get_by_hydro_batch(
    hydro_batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plant = plant_service.get_by_hydro_batch(db, hydro_batch_id)
    if not plant:
        raise HTTPException(404, f"No vision plant linked to hydro batch {hydro_batch_id}")
    ensure_plant_access(plant, current_user)
    return plant


@router.post("/link-batch/{hydro_batch_id}", response_model=PlantOut)
def link_batch(
    hydro_batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Idempotent: returns the existing linked VisionPlant, or creates one
    scoped to the caller's client_id."""
    plant = plant_service.link_or_create_from_hydro_batch(db, hydro_batch_id, current_user.client_id)
    ensure_plant_access(plant, current_user)
    return plant


# Camera routes
camera_router = APIRouter(prefix="/api/v1/cameras", tags=["AI Vision - Cameras"])


@camera_router.post("", response_model=CameraOut)
def create_camera(
    data: CameraCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return plant_service.create_camera(db, **data.model_dump(), client_id=current_user.client_id)


@camera_router.get("", response_model=List[CameraOut])
def list_cameras(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.is_super_admin():
        return plant_service.get_all_cameras(db)
    return plant_service.get_all_cameras_by_client(db, current_user.client_id)
