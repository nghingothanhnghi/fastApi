# app/ai_vision/services/image_service.py
from sqlalchemy.orm import Session
from fastapi import UploadFile, HTTPException, status
from app.ai_vision.models.image import PlantImage
from app.ai_vision.models.inference_job import AIInferenceJob
from app.ai_vision.integrations.storage_client import image_storage_service
from app.ai_vision.services.plant_service import plant_service
from app.ai_vision import config
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class ImageService:
    def ingest_image(self, db: Session, plant_id: int, file: UploadFile, camera_id: int = None) -> PlantImage:
        plant = plant_service.get_plant(db, plant_id)
        if not plant:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Plant {plant_id} not found")

        stored = image_storage_service.save(file)

        image = PlantImage(
            plant_id=plant_id,
            camera_id=camera_id,
            storage_path=stored["storage_path"],
            public_url=stored["public_url"],
            image_hash=stored["image_hash"],
            content_type=file.content_type,
            file_size_bytes=stored["file_size_bytes"],
            processing_status="uploaded",
        )
        db.add(image)
        db.commit()
        db.refresh(image)

        # Queue inference immediately rather than running it inline - heavy
        # AI work must never block the upload request.
        if config.AI_ENABLED:
            self.queue_inference(db, image)

        logger.info("AI vision image ingested", extra={"image_id": image.id, "plant_id": plant_id})
        return image

    def queue_inference(self, db: Session, image: PlantImage) -> AIInferenceJob:
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

    def get_image(self, db: Session, image_id: int) -> PlantImage:
        image = db.query(PlantImage).filter(PlantImage.id == image_id).first()
        if not image:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
        return image

    def get_job(self, db: Session, job_id: int) -> AIInferenceJob:
        job = db.query(AIInferenceJob).filter(AIInferenceJob.id == job_id).first()
        if not job:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Inference job not found")
        return job


image_service = ImageService()
