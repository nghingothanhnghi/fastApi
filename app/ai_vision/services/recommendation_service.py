# app/ai_vision/services/recommendation_service.py
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from typing import Optional, List, Tuple
from app.ai_vision.models.ai_recommendation import AIRecommendation
from app.ai_vision.models.plant_health import PlantHealthRecord
from app.ai_vision.models.plant_anomaly import PlantAnomaly

_TOPIC_TEXT = {
    "irrigation_flow": "Inspect the pump, tubing and flow sensor for this plant's zone.",
    "overwatering": "Review the irrigation schedule and water baseline for this plant's zone.",
    "drought": "Check the tank water level and refill if needed.",
    "heat": "Check ventilation and temperature control for this plant's zone.",
    "nutrient": "Inspect nutrient concentration (EC/PPM) for this plant's zone.",
    "light": "Inspect lighting schedule and intensity for this plant's zone.",
}
_TOPIC_PRIORITY = ["irrigation_flow", "drought", "overwatering", "heat", "nutrient", "light"]


class RecommendationService:
    """Every recommendation cites its evidence (non-empty `reasons`). Status
    stays `pending_review` - no path into hydro actuators from this module.

    Reasons use the thresholds hydro itself applies for the plant's device
    (via `anomalous_sensors`), never hard-coded numbers."""

    DEDUP_HOURS = 12

    def from_health_and_anomalies(
        self, db: Session, health_record: PlantHealthRecord, anomalies: list[PlantAnomaly]
    ) -> Optional[AIRecommendation]:
        if health_record.status not in ("warning", "critical") and not anomalies:
            return None

        reasons: List[str] = []
        indicators = health_record.visual_indicators or []

        for ind in indicators:
            reasons.append(f"Visual indicator detected: {ind.replace('_', ' ')}")
        for issue in (health_record.possible_issues or []):
            reasons.append(f"Possible issue flagged: {issue.get('issue')} (confidence {issue.get('confidence')})")

        sensor = health_record.sensor_snapshot or {}
        anomalous = sensor.get("anomalous_sensors") or []
        for a in anomalous:
            reasons.append(
                f"{a['label'].capitalize()} is {a['direction']} "
                f"({a['value']} vs configured {a['threshold']})"
            )

        fused = self._correlate_visual_and_sensor(indicators, anomalous, sensor)
        reasons.extend(msg for _, msg in fused)

        ctx = sensor.get("context") or {}
        if ctx.get("stage"):
            reasons.append(f"Batch is in stage '{ctx['stage']}' (day {ctx.get('days_growing')})")

        for anomaly in anomalies:
            reasons.append(anomaly.description)

        if not reasons:
            reasons.append(f"Health score is {health_record.health_score} ({health_record.status})")

        text = self._build_text(health_record, {t for t, _ in fused})
        severity = "high" if (health_record.status == "critical" or fused) else "medium"

        # Same plant, same advice, same severity, still unreviewed -> don't pile up duplicates
        cutoff = datetime.utcnow() - timedelta(hours=self.DEDUP_HOURS)
        duplicate = (
            db.query(AIRecommendation)
            .filter(
                AIRecommendation.plant_id == health_record.plant_id,
                AIRecommendation.recommendation == text,
                AIRecommendation.severity == severity,
                AIRecommendation.status == "pending_review",
                AIRecommendation.created_at >= cutoff,
            )
            .first()
        )
        if duplicate:
            return duplicate

        recommendation = AIRecommendation(
            plant_id=health_record.plant_id,
            health_record_id=health_record.id,
            anomaly_id=anomalies[0].id if anomalies else None,
            recommendation=text,
            reasons=reasons,
            severity=severity,
            confidence=health_record.confidence,
            status="pending_review",
        )
        db.add(recommendation)
        db.flush()
        return recommendation

    @staticmethod
    def _correlate_visual_and_sensor(
        visual_indicators: List[str], anomalous_sensors: List[dict], sensor: Optional[dict] = None
    ) -> List[Tuple[str, str]]:
        """Visual symptom + independent hydro evidence in the same window -> (topic, message)."""
        sensor = sensor or {}
        matches: List[Tuple[str, str]] = []
        indicators = set(visual_indicators)
        by_sensor = {a["sensor"]: a for a in anomalous_sensors}
        excessive = (sensor.get("irrigation") or {}).get("excessive_usage_alert")

        if "leaf_yellowing" in indicators:
            for key in ("ec", "ppm"):
                a = by_sensor.get(key)
                if a and a["direction"] == "low":
                    matches.append(("nutrient",
                        f"Leaf yellowing coincides with low {a['label']} ({a['value']} < {a['threshold']}) "
                        f"in the same window - consistent with nutrient deficiency, not a lighting/camera artifact"))
            if excessive:
                matches.append(("overwatering",
                    f"Leaf yellowing coincides with an excessive-water-usage alert "
                    f"(+{excessive['difference_percent']}% vs baseline) - possible overwatering/root stress"))

        if "leaf_browning" in indicators:
            a = by_sensor.get("temperature")
            if a and a["direction"] == "high":
                matches.append(("heat",
                    f"Leaf browning coincides with elevated temperature ({a['value']} > {a['threshold']}) "
                    f"- consistent with heat/leaf-burn stress"))
            a = by_sensor.get("water_level")
            if a and a["direction"] == "low":
                matches.append(("drought",
                    f"Leaf browning coincides with low water level ({a['value']} < {a['threshold']}) "
                    f"- consistent with drought stress"))
            a = by_sensor.get("flow_rate")
            if a and a["direction"] == "low":
                matches.append(("irrigation_flow",
                    f"Leaf browning coincides with low pump flow ({a['value']} L/min < {a['threshold']}) "
                    f"- consistent with an irrigation shortfall"))

        if "low_canopy_greenness" in indicators:
            a = by_sensor.get("light")
            if a and a["direction"] == "low":
                rain = " during rain" if sensor.get("rain_detected") else ""
                matches.append(("light",
                    f"Reduced canopy greenness coincides with low light{rain} "
                    f"({a['value']} < {a['threshold']}) - consistent with light-limited growth"))

        return matches

    @staticmethod
    def _build_text(health_record: PlantHealthRecord, topics: set) -> str:
        for topic in _TOPIC_PRIORITY:
            if topic in topics:
                return _TOPIC_TEXT[topic]
        if "leaf_yellowing" in (health_record.visual_indicators or []):
            return "Inspect nutrient concentration and lighting for this plant."
        if health_record.status == "critical":
            return "Manually inspect this plant as soon as possible."
        return "Review this plant's recent images and sensor history."


recommendation_service = RecommendationService()