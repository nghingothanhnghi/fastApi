# app/ai_vision/jobs/inference_job.py
from app.database import SessionLocal
from app.ai_vision.models.inference_job import AIInferenceJob
from app.ai_vision.controllers.vision_controller import run_full_pipeline
from app.core.logging_config import get_logger

logger = get_logger("ai_vision.inference_job")


def process_queued_inference_jobs():
    """Polling worker, same pattern as app/cms/jobs/scheduled_publish_job.py.
    Swap for a real queue consumer (Celery/RQ against Redis, if the project
    adds one) without changing run_full_pipeline()."""
    db = SessionLocal()
    try:
        jobs = db.query(AIInferenceJob).filter(AIInferenceJob.status == "queued").limit(10).all()
        for job in jobs:
            run_full_pipeline(db, job)
        if jobs:
            logger.info(f"[AIVision] Processed {len(jobs)} queued inference job(s)")
    except Exception as e:
        logger.error(f"[AIVision] Inference job poll failed: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()
