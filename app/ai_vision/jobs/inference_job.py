# app/ai_vision/jobs/inference_job.py
from app.database import SessionLocal
from app.ai_vision.models.inference_job import AIInferenceJob
from app.ai_vision.controllers.vision_controller import run_full_pipeline
from app.ai_vision.services.inference_job_service import inference_job_service
from app.core.logging_config import get_logger

logger = get_logger("ai_vision.inference_job")

def process_queued_inference_jobs():
    """Polling worker, same pattern as app/cms/jobs/scheduled_publish_job.py.
    Swap for a real queue consumer (Celery/RQ against Redis, if the project
    adds one) without changing run_full_pipeline()."""
    db = SessionLocal()
    try:
        requeued = inference_job_service.requeue_expired_leases(db)
        if requeued:
            logger.warning("[AIVision] Requeued %s expired inference job(s)", requeued)
        job_ids = [j.id for j in db.query(AIInferenceJob.id).filter(AIInferenceJob.status == "queued").limit(10).all()]
        for job_id in job_ids:
            if not inference_job_service.claim(db, job_id):
                continue  # another worker got it first
            job = inference_job_service.get(db, job_id)
            run_full_pipeline(db, job)
        if job_ids:
            logger.info(f"[AIVision] Processed {len(job_ids)} queued inference job(s)")
    except Exception as e:
        logger.error(f"[AIVision] Inference job poll failed: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()
