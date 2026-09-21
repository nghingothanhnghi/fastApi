# app/ai_vision/controllers/vision_controller.py
from sqlalchemy.orm import Session
from datetime import datetime
from app.ai_vision.services.image_service import image_service
from app.ai_vision.services.vision_service import vision_service
from app.ai_vision.services.growth_service import growth_service
from app.ai_vision.services.health_service import health_service
from app.ai_vision.services.anomaly_service import anomaly_service
from app.ai_vision.services.recommendation_service import recommendation_service
from app.ai_vision.models.inference_job import AIInferenceJob
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def run_full_pipeline(db: Session, job: AIInferenceJob) -> None:
    """Persist all derived analysis rows atomically for an already-claimed job."""
    image = image_service.get_image(db, job.image_id)
    image.processing_status = "processing"

    try:
        predictions = vision_service.run_predictions(db, image)
        by_task = {p.task: p for p in predictions}

        growth_anomalies = []
        disease_anomalies = []

        if "detection" in by_task:
            growth_record = growth_service.record_growth(db, image, by_task["detection"])
            growth_anomalies = anomaly_service.check_growth(db, growth_record)

        # V3: disease/pest indicators feed into the same debounced anomaly
        # pipeline as growth/health, then flow into the recommendation below
        # alongside them.
        if "disease" in by_task:
            disease_anomalies = anomaly_service.check_disease(db, image.plant_id, by_task["disease"])

        if "health" in by_task:
            health_record = health_service.compute_health(db, image, by_task["health"])
            health_anomalies = anomaly_service.check_health(db, health_record)
            recommendation_service.from_health_and_anomalies(
                db, health_record, growth_anomalies + disease_anomalies + health_anomalies
            )

        job.status = "completed"
        job.completed_at = datetime.utcnow()
        image.processing_status = "completed"
        db.commit()   # single durable commit for predictions + growth + health + disease + anomalies + recommendation + job status

    except Exception as e:
        logger.error(f"AI vision pipeline failed for image {image.id}: {e}", exc_info=True)
        db.rollback()   # discards ALL partial analysis rows, not just the flush buffer
        job.status = "failed"
        job.error_message = str(e)
        image.processing_status = "failed"
        db.commit()
