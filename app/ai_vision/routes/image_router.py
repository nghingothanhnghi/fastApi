# app/ai_vision/routes/image_router.py
from fastapi import APIRouter, Depends, UploadFile, File, Query, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.user.utils.token import get_current_user
from app.user.models.user import User
from app.ai_vision.services.image_service import image_service
from app.ai_vision.services.plant_service import plant_service
from app.ai_vision.helpers.access_helper import ensure_plant_access
from app.ai_vision.schemas.image_schema import PlantImageOut

router = APIRouter(prefix="/api/v1/vision/images", tags=["AI Vision - Images"])


@router.post("", response_model=PlantImageOut)
def upload_image(
    plant_id: int = Query(...),
    camera_id: int = Query(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ingest an image and queue AI inference. Inference always runs
    asynchronously - see /api/v1/ai/inference/{job_id} for status."""
    plant = plant_service.get_plant(db, plant_id)
    if not plant:
        raise HTTPException(404, f"Plant {plant_id} not found")
    ensure_plant_access(plant, current_user)
    return image_service.ingest_image(db, plant_id, file, camera_id)


@router.get("/{image_id}", response_model=PlantImageOut)
def get_image(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    image = image_service.get_image(db, image_id)
    plant = plant_service.get_plant(db, image.plant_id)
    if plant:
        ensure_plant_access(plant, current_user)
    return image
