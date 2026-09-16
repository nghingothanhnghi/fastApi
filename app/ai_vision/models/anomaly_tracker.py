# app/ai_vision/models/anomaly_tracker.py
from sqlalchemy import Column, Integer, String, Float, DateTime, UniqueConstraint, func
from app.database import Base


class AnomalyTracker(Base):
    """
    Debounce state for anomaly detection, one row per (plant_id, anomaly_type).

    AnomalyService no longer raises a PlantAnomaly off a single
    threshold-crossing evaluation. Instead every evaluation (growth check,
    health check, ...) updates this row's `consecutive_count`:
      - condition still crossing threshold -> increment
      - condition clean -> reset to 0

    A PlantAnomaly is only created once `consecutive_count` reaches
    `app.ai_vision.config.ANOMALY_DEBOUNCE_COUNT`, at which point the streak
    is reset (`last_triggered_at` set, count back to 0) so the next anomaly
    needs a fresh run of consecutive readings rather than firing again on
    every subsequent evaluation.

    Lives in its own table (not in-memory) so the streak survives process
    restarts and is shared correctly across scheduler workers.
    """
    __tablename__ = "ai_vision_anomaly_trackers"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, nullable=False, index=True)
    anomaly_type = Column(String(50), nullable=False, index=True)

    consecutive_count = Column(Integer, nullable=False, default=0)
    last_evaluated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)

    # Last observed evidence value (e.g. deviation_from_baseline_pct or
    # health_score) — kept for debugging/visibility without re-querying the
    # source growth/health tables.
    last_value = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("plant_id", "anomaly_type", name="uq_anomaly_tracker_plant_type"),
    )

    def __repr__(self):
        return (
            f"<AnomalyTracker(plant_id={self.plant_id}, type={self.anomaly_type}, "
            f"streak={self.consecutive_count})>"
        )
