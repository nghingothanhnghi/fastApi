# app/ai_vision/services/recommendation_service.py
from sqlalchemy.orm import Session
from typing import Optional, List
from app.ai_vision.models.ai_recommendation import AIRecommendation
from app.ai_vision.models.plant_health import PlantHealthRecord
from app.ai_vision.models.plant_anomaly import PlantAnomaly


class RecommendationService:
    """Every recommendation must cite the evidence that produced it - never
    emit a bare instruction. This is enforced by requiring a non-empty
    `reasons` list at the model level.

    V4: reasons now include explicit visual+sensor fusion when a visual
    symptom co-occurs with a sensor reading that's independently out of
    range in the same time window (see _correlate_visual_and_sensor) -
    that's stronger evidence than listing the two facts side by side, so
    it's surfaced as its own reason and bumps severity.
    """

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

        # V4: fused visual+sensor correlations, computed from the same
        # window's anomalous_sensors list attached by
        # hydroponic_client.SensorFusionService.get_window().
        fused_matches = self._correlate_visual_and_sensor(
            health_record.visual_indicators or [], sensor.get("anomalous_sensors") or []
        )
        reasons.extend(fused_matches)

        for anomaly in anomalies:
            reasons.append(anomaly.description)

        if not reasons:
            reasons.append(f"Health score is {health_record.health_score} ({health_record.status})")

        text = self._build_text(health_record)

        # Co-occurring visual + sensor evidence is stronger than either
        # alone, so it escalates severity even if the health status itself
        # was only "warning".
        severity = "high" if (health_record.status == "critical" or fused_matches) else "medium"

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
    def _correlate_visual_and_sensor(visual_indicators: List[str], anomalous_sensors: List[dict]) -> List[str]:
        """
        V4 fusion: when a visual symptom co-occurs with a sensor reading
        that's independently out of range in the same window, state the
        correlation explicitly instead of the caller having to notice two
        separate facts point the same way.
        """
        matches = []
        indicators = set(visual_indicators)
        by_sensor = {a["sensor"]: a for a in anomalous_sensors}

        if "leaf_yellowing" in indicators:
            for key in ("ec", "ppm"):
                a = by_sensor.get(key)
                if a and a["direction"] == "low":
                    matches.append(
                        f"Leaf yellowing coincides with low {a['label']} "
                        f"({a['value']} < {a['threshold']}) in the same window - "
                        f"consistent with nutrient deficiency rather than a lighting/camera artifact"
                    )

        if "leaf_browning" in indicators:
            a = by_sensor.get("temperature")
            if a and a["direction"] == "high":
                matches.append(
                    f"Leaf browning coincides with elevated temperature "
                    f"({a['value']} > {a['threshold']}) - consistent with heat/leaf-burn stress"
                )
            a = by_sensor.get("water_level")
            if a and a["direction"] == "low":
                matches.append(
                    f"Leaf browning coincides with low water level "
                    f"({a['value']} < {a['threshold']}) - consistent with drought stress"
                )

        if "low_canopy_greenness" in indicators:
            a = by_sensor.get("light")
            if a and a["direction"] == "low":
                matches.append(
                    f"Reduced canopy greenness coincides with low light "
                    f"({a['value']} < {a['threshold']}) - consistent with light-limited growth"
                )

        return matches

    @staticmethod
    def _build_text(health_record: PlantHealthRecord) -> str:
        if "leaf_yellowing" in (health_record.visual_indicators or []):
            return "Inspect nutrient concentration and lighting for this plant."
        if health_record.status == "critical":
            return "Manually inspect this plant as soon as possible."
        return "Review this plant's recent images and sensor history."


recommendation_service = RecommendationService()
