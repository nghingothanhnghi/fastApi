from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.ai_vision import config
from app.ai_vision.models.inference_job import AIInferenceJob

if TYPE_CHECKING:
    from app.ai_vision.models.image import PlantImage


class InferenceJobService:
    """Owns the durable state transitions of inference jobs.

    A claim is committed before inference starts so concurrent scheduler
    instances cannot both process a queued job. Pipeline result rows remain in
    the caller's transaction and are committed only by the controller.
    """

    ACTIVE_STATUSES = ("queued", "processing")

    def get_or_create_active(self, db: Session, image: "PlantImage") -> AIInferenceJob:
        job = (
            db.query(AIInferenceJob)
            .filter(
                AIInferenceJob.image_id == image.id,
                AIInferenceJob.status.in_(self.ACTIVE_STATUSES),
            )
            .order_by(AIInferenceJob.queued_at.desc(), AIInferenceJob.id.desc())
            .first()
        )
        if job:
            return job

        job = AIInferenceJob(
            image_id=image.id,
            model_name=config.AI_MODEL_NAME,
            model_version=config.AI_MODEL_VERSION,
            status="queued",
        )
        image.processing_status = "queued"
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def claim(self, db: Session, job_id: int) -> bool:
        claimed = (
            db.query(AIInferenceJob)
            .filter(AIInferenceJob.id == job_id, AIInferenceJob.status == "queued")
            .update(
                {"status": "processing", "started_at": datetime.utcnow()},
                synchronize_session=False,
            )
        )
        db.commit()
        return claimed == 1

    def get(self, db: Session, job_id: int) -> Optional[AIInferenceJob]:
        return db.get(AIInferenceJob, job_id)

    def requeue_expired_leases(self, db: Session) -> int:
        cutoff = datetime.utcnow() - timedelta(seconds=config.AI_JOB_LEASE_SECONDS)
        requeued = (
            db.query(AIInferenceJob)
            .filter(
                AIInferenceJob.status == "processing",
                or_(
                    AIInferenceJob.started_at < cutoff,
                    AIInferenceJob.started_at.is_(None),
                ),
            )
            .update(
                {"status": "queued", "started_at": None},
                synchronize_session=False,
            )
        )
        if requeued:
            db.commit()
        return requeued


inference_job_service = InferenceJobService()
