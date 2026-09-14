# app/ai_vision/services/vision_service.py
from sqlalchemy.orm import Session
from app.ai_vision.models.image import PlantImage
from app.ai_vision.models.vision_prediction import VisionPrediction
from app.ai_vision.ai.inference.inference_manager import inference_manager
from app.ai_vision.integrations.camera_client import load_image_from_path
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class VisionService:
    def run_predictions(self, db: Session, image: PlantImage) -> list[VisionPrediction]:
        cv_image = load_image_from_path(image.storage_path)
        if cv_image is None:
            raise ValueError(f"Could not load image at {image.storage_path}")

        results = inference_manager.run_all(["detection", "health"], cv_image)

        predictions = []
        for result in results:
            prediction = VisionPrediction(
                image_id=image.id,
                plant_id=image.plant_id,
                model_name=result["model_name"],
                model_version=result["model_version"],
                task=result["task"],
                confidence=result["confidence"],
                inference_time_ms=result["inference_time_ms"],
                raw_output=result["raw_output"],
            )
            db.add(prediction)
            predictions.append(prediction)

        db.commit()
        for p in predictions:
            db.refresh(p)

        logger.info(
            "Vision predictions completed",
            extra={"image_id": image.id, "plant_id": image.plant_id, "count": len(predictions)},
        )
        return predictions


vision_service = VisionService()
