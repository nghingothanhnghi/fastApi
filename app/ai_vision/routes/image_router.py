# app/ai_vision/routes/image_router.py
from fastapi import APIRouter, Depends, UploadFile, File, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.ai_vision.services.image_service import image_service
from app.ai_vision.schemas.image_schema import PlantImageOut

router = APIRouter(prefix="/api/v1/vision/images", tags=["AI Vision - Images"])


@router.post("", response_model=PlantImageOut)
def upload_image(
    plant_id: int = Query(...),
    camera_id: int = Query(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Ingest an image and queue AI inference. Inference always runs
    asynchronously - see /api/v1/ai/inference/{job_id} for status."""
    return image_service.ingest_image(db, plant_id, file, camera_id)


@router.get("/{image_id}", response_model=PlantImageOut)
def get_image(image_id: int, db: Session = Depends(get_db)):
    return image_service.get_image(db, image_id)
