# app/ai_vision/services/anomaly_service.py
from sqlalchemy.orm import Session

from app.ai_vision.models.plant_anomaly import PlantAnomaly
from app.ai_vision.models.plant_growth import PlantGrowthRecord
from app.ai_vision.models.plant_health import PlantHealthRecord
from app.ai_vision.models.vision_prediction import VisionPrediction
from app.ai_vision.services.growth_service import growth_service
from app.ai_vision.repositories.anomaly_repository import anomaly_tracker_repository
from app.ai_vision import config


class AnomalyService:
    """
    Debounced threshold checks: a PlantAnomaly is only persisted once the
    same condition has been observed on config.ANOMALY_DEBOUNCE_COUNT
    consecutive evaluations for that (plant_id, anomaly_type) pair. A
    single clean reading resets the streak.

    Debounce state lives in AnomalyTracker (see
    repositories/anomaly_repository.py) so it survives across job runs and
    process restarts, and is safe under the scheduler's requeue/lease model
    since it's a plain DB row, not in-memory state.
    """

    def check_growth(self, db: Session, growth_record: PlantGrowthRecord) -> list[PlantAnomaly]:
        is_anomalous = growth_service.is_growth_anomalous(growth_record)

        tracker = anomaly_tracker_repository.record_evaluation(
            db,
            plant_id=growth_record.plant_id,
            anomaly_type="growth_slowdown",
            is_crossing=is_anomalous,
            value=(
                growth_record.deviation_from_baseline_pct
                if growth_record.deviation_from_baseline_pct is not None
                else growth_record.growth_rate_pct_per_day
            ),
        )

        if not is_anomalous or tracker.consecutive_count < config.ANOMALY_DEBOUNCE_COUNT:
            return []

        deviation = growth_record.deviation_from_baseline_pct
        growth_rate = growth_record.growth_rate_pct_per_day

        if deviation is not None:
            severity = "medium" if deviation > -50 else "high"
            description = (
                f"Growth rate deviates {deviation}% from baseline "
                f"{growth_record.baseline_growth_rate_pct_per_day}%/day "
                f"across {tracker.consecutive_count} consecutive readings"
            )
        else:
            # Zero-baseline case: no meaningful "%" deviation exists to
            # report; this was flagged via the absolute-rate fallback instead
            # (see growth_service.is_growth_anomalous).
            severity = "high" if abs(growth_rate) >= (config.GROWTH_ANOMALY_ABS_PCT_PER_DAY * 2) else "medium"
            description = (
                f"Growth rate is {growth_rate}%/day against a flat (0%/day) baseline "
                f"across {tracker.consecutive_count} consecutive readings - "
                f"flagged via absolute-change threshold (>= {config.GROWTH_ANOMALY_ABS_PCT_PER_DAY}%/day)"
            )

        anomaly = self._create(
            db, growth_record.plant_id, "growth_slowdown",
            severity=severity,
            description=description,
            evidence={
                "growth_rate_pct_per_day": growth_record.growth_rate_pct_per_day,
                "baseline_growth_rate_pct_per_day": growth_record.baseline_growth_rate_pct_per_day,
                "deviation_from_baseline_pct": growth_record.deviation_from_baseline_pct,
                "consecutive_readings": tracker.consecutive_count,
            },
        )
        anomaly_tracker_repository.mark_triggered(db, tracker)
        return [anomaly]

    def check_health(self, db: Session, health_record: PlantHealthRecord) -> list[PlantAnomaly]:
        is_anomalous = health_record.status in ("warning", "critical")

        tracker = anomaly_tracker_repository.record_evaluation(
            db,
            plant_id=health_record.plant_id,
            anomaly_type="visual_change",
            is_crossing=is_anomalous,
            value=float(health_record.health_score),
        )

        if not is_anomalous or tracker.consecutive_count < config.ANOMALY_DEBOUNCE_COUNT:
            return []

        anomaly = self._create(
            db, health_record.plant_id, "visual_change",
            severity="high" if health_record.status == "critical" else "medium",
            description=(
                f"Health score dropped to {health_record.health_score} ({health_record.status}) "
                f"across {tracker.consecutive_count} consecutive readings"
            ),
            evidence={
                "health_score": health_record.health_score,
                "visual_indicators": health_record.visual_indicators,
                "sensor_snapshot": health_record.sensor_snapshot,
                "consecutive_readings": tracker.consecutive_count,
            },
        )
        anomaly_tracker_repository.mark_triggered(db, tracker)
        return [anomaly]

    def check_disease(self, db: Session, plant_id: int, disease_prediction: VisionPrediction) -> list[PlantAnomaly]:
        """
        V3: same debounce mechanism as check_growth/check_health, applied to
        the classical-CV disease/pest signal (see
        ai/inference/disease_classifier.py). A single frame with a stray
        shadow or leaf overlap won't raise an anomaly - it takes
        config.ANOMALY_DEBOUNCE_COUNT consecutive readings with the same
        indicator present.
        """
        raw = disease_prediction.raw_output
        indicators = raw.get("visual_indicators") or []
        is_anomalous = bool(indicators)

        tracker = anomaly_tracker_repository.record_evaluation(
            db,
            plant_id=plant_id,
            anomaly_type="disease_pest",
            is_crossing=is_anomalous,
            value=raw.get("spot_area_ratio"),
        )

        if not is_anomalous or tracker.consecutive_count < config.ANOMALY_DEBOUNCE_COUNT:
            return []

        severity = (
            "high" if ("leaf_spots" in indicators and (raw.get("spot_area_ratio") or 0) > 0.03)
            else "medium"
        )
        description = (
            f"Leaf disease/pest indicators detected ({', '.join(indicators)}) "
            f"across {tracker.consecutive_count} consecutive readings "
            f"(solidity={raw.get('leaf_solidity')}, spot_count={raw.get('spot_count')})"
        )

        anomaly = self._create(
            db, plant_id, "disease_pest",
            severity=severity,
            description=description,
            evidence={**raw, "consecutive_readings": tracker.consecutive_count},
        )
        anomaly_tracker_repository.mark_triggered(db, tracker)
        return [anomaly]

    def _create(
        self, db: Session, plant_id: int, anomaly_type: str, severity: str, description: str, evidence: dict
    ) -> PlantAnomaly:
        anomaly = PlantAnomaly(
            plant_id=plant_id, anomaly_type=anomaly_type, severity=severity,
            description=description, evidence=evidence,
        )
        db.add(anomaly)
        db.flush()
        return anomaly


anomaly_service = AnomalyService()
