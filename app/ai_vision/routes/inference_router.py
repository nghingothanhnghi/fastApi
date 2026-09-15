# app/ai_vision/routes/inference_router.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.ai_vision.services.image_service import image_service
from app.ai_vision.services.inference_job_service import inference_job_service
from app.ai_vision.controllers.vision_controller import run_full_pipeline
from app.ai_vision.schemas.image_schema import InferenceJobOut

router = APIRouter(prefix="/api/v1", tags=["AI Vision - Inference"])


@router.post("/vision/analyze/{image_id}", response_model=InferenceJobOut)
def analyze_image_now(image_id: int, db: Session = Depends(get_db)):
    """Manual re-analyze - runs synchronously for admin/debug use. Regular
    ingestion always goes through the async queue (image_router)."""
    image = image_service.get_image(db, image_id)
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
def get_inference_job(job_id: int, db: Session = Depends(get_db)):
    return image_service.get_job(db, job_id)
