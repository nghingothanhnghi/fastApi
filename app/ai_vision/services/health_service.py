# app/ai_vision/services/health_service.py
from sqlalchemy.orm import Session
from datetime import datetime
from app.ai_vision.models.plant_health import PlantHealthRecord
from app.ai_vision.models.vision_prediction import VisionPrediction
from app.ai_vision.models.image import PlantImage
from app.ai_vision.integrations.hydroponic_client import sensor_fusion_service
from app.ai_vision.services.plant_service import plant_service
from app.ai_vision import config


class HealthService:
    def compute_health(
        self, db: Session, image: PlantImage, health_prediction: VisionPrediction
    ) -> PlantHealthRecord:
        raw = health_prediction.raw_output
        visual_indicators = raw.get("visual_indicators", [])
        possible_issues = raw.get("possible_issues", [])

        plant = plant_service.get_plant(db, image.plant_id)
        # Device is resolved from the plant (batch zone > camera device >
        # tenant-scoped location), not from a bare location string.
        sensor_snapshot = sensor_fusion_service.get_window(
            db, plant=plant, timestamp=image.captured_at or datetime.utcnow()
        )

        # Simple, explainable scoring - seam for a trained regression head later.
        score = 100
        score -= 15 * len(visual_indicators)
        score -= 10 * len(possible_issues)
        score = max(0, min(100, score))

        record = PlantHealthRecord(
            plant_id=image.plant_id,
            image_id=image.id,
            health_score=score,
            status=self._score_to_status(score),
            visual_indicators=visual_indicators,
            possible_issues=possible_issues,
            sensor_snapshot=sensor_snapshot,
            confidence=health_prediction.confidence,
            model_name=health_prediction.model_name,
            model_version=health_prediction.model_version,
        )
        db.add(record)
        db.flush()
        return record

    @staticmethod
    def _score_to_status(score: int) -> str:
        if score >= 90:
            return "healthy"
        if score >= config.PLANT_HEALTH_WARNING_THRESHOLD:
            return "normal"
        if score >= config.PLANT_HEALTH_CRITICAL_THRESHOLD:
            return "warning"
        return "critical"


health_service = HealthService()