# app/ai_vision/routes/inference_router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.user.utils.token import get_current_user
from app.user.models.user import User
from app.ai_vision.services.image_service import image_service
from app.ai_vision.services.plant_service import plant_service
from app.ai_vision.helpers.access_helper import ensure_plant_access
from app.ai_vision.services.inference_job_service import inference_job_service
from app.ai_vision.controllers.vision_controller import run_full_pipeline
from app.ai_vision.schemas.image_schema import InferenceJobOut

router = APIRouter(prefix="/api/v1", tags=["AI Vision - Inference"])

def _ensure_image_access(db: Session, image_id: int, current_user: User):
    image = image_service.get_image(db, image_id)
    plant = plant_service.get_plant(db, image.plant_id)
    if plant:
        ensure_plant_access(plant, current_user)
    return image

@router.post("/vision/analyze/{image_id}", response_model=InferenceJobOut)
def analyze_image_now(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manual re-analyze - runs synchronously for admin/debug use. Regular
    ingestion always goes through the async queue (image_router)."""
    image = _ensure_image_access(db, image_id, current_user)

    job = inference_job_service.get_or_create_active(db, image)
    if job.status == "processing":
        return job

    if not inference_job_service.claim(db, job.id):
        return inference_job_service.get(db, job.id)

    job = inference_job_service.get(db, job.id)
    run_full_pipeline(db, job)
    db.refresh(job)
    return job


@router.get("/ai/inference/{job_id}", response_model=InferenceJobOut)
def get_inference_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = image_service.get_job(db, job_id)
    _ensure_image_access(db, job.image_id, current_user)
    return job
