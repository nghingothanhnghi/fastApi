# app/ai_vision/services/recommendation_service.py
from sqlalchemy.orm import Session
from typing import Optional
from app.ai_vision.models.ai_recommendation import AIRecommendation
from app.ai_vision.models.plant_health import PlantHealthRecord
from app.ai_vision.models.plant_anomaly import PlantAnomaly


class RecommendationService:
    """Every recommendation must cite the evidence that produced it - never
    emit a bare instruction. This is enforced by requiring a non-empty
    `reasons` list at the model level."""

    def from_health_and_anomalies(
        self, db: Session, health_record: PlantHealthRecord, anomalies: list[PlantAnomaly]
    ) -> Optional[AIRecommendation]:
        if health_record.status not in ("warning", "critical") and not anomalies:
            return None

        reasons = []
        if "leaf_yellowing" in (health_record.visual_indicators or []):
            reasons.append("Visual leaf yellowing detected")
        for issue in (health_record.possible_issues or []):
            reasons.append(f"Possible issue flagged: {issue.get('issue')} (confidence {issue.get('confidence')})")

        sensor = health_record.sensor_snapshot or {}
        ec = sensor.get("ec")
        if ec is not None and ec < 1.2:
            reasons.append(f"EC ({ec}) is below the configured baseline")

        for anomaly in anomalies:
            reasons.append(anomaly.description)

        if not reasons:
            reasons.append(f"Health score is {health_record.health_score} ({health_record.status})")

        text = self._build_text(health_record)

        recommendation = AIRecommendation(
            plant_id=health_record.plant_id,
            health_record_id=health_record.id,
            anomaly_id=anomalies[0].id if anomalies else None,
            recommendation=text,
            reasons=reasons,
            severity="high" if health_record.status == "critical" else "medium",
            confidence=health_record.confidence,
            status="pending_review",
        )
        db.add(recommendation)
        db.flush()
        return recommendation

    @staticmethod
    def _build_text(health_record: PlantHealthRecord) -> str:
        if "leaf_yellowing" in (health_record.visual_indicators or []):
            return "Inspect nutrient concentration and lighting for this plant."
        if health_record.status == "critical":
            return "Manually inspect this plant as soon as possible."
        return "Review this plant's recent images and sensor history."


recommendation_service = RecommendationService()
