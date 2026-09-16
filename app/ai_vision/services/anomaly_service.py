# app/ai_vision/services/anomaly_service.py
from sqlalchemy.orm import Session
from app.ai_vision.models.plant_anomaly import PlantAnomaly
from app.ai_vision.models.plant_growth import PlantGrowthRecord
from app.ai_vision.models.plant_health import PlantHealthRecord
from app.ai_vision.services.growth_service import growth_service
from app.ai_vision.repositories.anomaly_repository import anomaly_tracker_repository
from app.ai_vision import config


class AnomalyService:
    """V1 keeps this intentionally simple (direct threshold comparison) -
    the debounce/persistence requirement is the next increment: only raise
    once N consecutive readings cross the threshold, tracked via a rolling
    count per (plant_id, anomaly_type), not on a single sample."""

    def check_growth(self, db: Session, growth_record: PlantGrowthRecord) -> list[PlantAnomaly]:
        anomalies = []
        if growth_service.is_growth_anomalous(growth_record):
            deviation = growth_record.deviation_from_baseline_pct
            growth_rate = growth_record.growth_rate_pct_per_day

            if deviation is not None:
                severity = "medium" if deviation > -50 else "high"
                description = (
                    f"Growth rate deviates {deviation}% "
                    f"from baseline {growth_record.baseline_growth_rate_pct_per_day}%/day"
                )
            else:
                # Zero-baseline case: no meaningful "%" deviation exists to report;
                # this was flagged via the absolute-rate fallback instead.
                severity = "high" if abs(growth_rate) >= (config.GROWTH_ANOMALY_ABS_PCT_PER_DAY * 2) else "medium"
                description = (
                    f"Growth rate is {growth_rate}%/day against a flat (0%/day) baseline — "
                    f"flagged via absolute-change threshold (>= {config.GROWTH_ANOMALY_ABS_PCT_PER_DAY}%/day)"
                )

            anomalies.append(self._create(
                db, growth_record.plant_id, "growth_slowdown",
                severity=severity,
                description=description,
                evidence={
                    "growth_rate_pct_per_day": growth_record.growth_rate_pct_per_day,
                    "baseline_growth_rate_pct_per_day": growth_record.baseline_growth_rate_pct_per_day,
                    "deviation_from_baseline_pct": growth_record.deviation_from_baseline_pct,
                },
            ))
        return anomalies

    def check_health(self, db: Session, health_record: PlantHealthRecord) -> list[PlantAnomaly]:
        anomalies = []
        if health_record.status in ("warning", "critical"):
            anomalies.append(self._create(
                db, health_record.plant_id, "visual_change",
                severity="high" if health_record.status == "critical" else "medium",
                description=f"Health score dropped to {health_record.health_score} ({health_record.status})",
                evidence={
                    "health_score": health_record.health_score,
                    "visual_indicators": health_record.visual_indicators,
                    "sensor_snapshot": health_record.sensor_snapshot,
                },
            ))
        return anomalies

    def _create(self, db: Session, plant_id: int, anomaly_type: str, severity: str, description: str, evidence: dict) -> PlantAnomaly:
        anomaly = PlantAnomaly(
            plant_id=plant_id, anomaly_type=anomaly_type, severity=severity,
            description=description, evidence=evidence,
        )
        db.add(anomaly)
        db.flush()
        return anomaly


anomaly_service = AnomalyService()
