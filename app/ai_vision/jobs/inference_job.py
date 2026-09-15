# app/ai_vision/jobs/inference_job.py
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.ai_vision.models.inference_job import AIInferenceJob
from app.ai_vision.controllers.vision_controller import run_full_pipeline
from app.core.logging_config import get_logger

logger = get_logger("ai_vision.inference_job")


def _claim_job(db: Session, job_id: int) -> bool:
    result = db.query(AIInferenceJob).filter(
        AIInferenceJob.id == job_id,
        AIInferenceJob.status == "queued",
    ).update({"status": "processing", "started_at": datetime.utcnow()})
    db.commit()
    return result == 1

def process_queued_inference_jobs():
    """Polling worker, same pattern as app/cms/jobs/scheduled_publish_job.py.
    Swap for a real queue consumer (Celery/RQ against Redis, if the project
    adds one) without changing run_full_pipeline()."""
    db = SessionLocal()
    try:
        job_ids = [j.id for j in db.query(AIInferenceJob.id).filter(AIInferenceJob.status == "queued").limit(10).all()]
        for job_id in job_ids:
            if not _claim_job(db, job_id):
                continue  # another worker got it first
            job = db.query(AIInferenceJob).get(job_id)
            run_full_pipeline(db, job)
        if job_ids:
            logger.info(f"[AIVision] Processed {len(job_ids)} queued inference job(s)")
    except Exception as e:
        logger.error(f"[AIVision] Inference job poll failed: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()
