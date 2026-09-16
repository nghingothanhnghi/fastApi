# app/ai_vision/repositories/anomaly_repository.py
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.ai_vision.models.anomaly_tracker import AnomalyTracker


class AnomalyTrackerRepository:
    """
    Persistence for AnomalyService's debounce state (see AnomalyTracker).
    Rows are never deleted — a clean reading just resets consecutive_count
    to 0 rather than removing the tracker, so history (last_value,
    last_triggered_at) is preserved for debugging.
    """

    def get(self, db: Session, plant_id: int, anomaly_type: str) -> Optional[AnomalyTracker]:
        return (
            db.query(AnomalyTracker)
            .filter(AnomalyTracker.plant_id == plant_id, AnomalyTracker.anomaly_type == anomaly_type)
            .first()
        )

    def get_or_create(self, db: Session, plant_id: int, anomaly_type: str) -> AnomalyTracker:
        tracker = self.get(db, plant_id, anomaly_type)
        if tracker:
            return tracker
        tracker = AnomalyTracker(plant_id=plant_id, anomaly_type=anomaly_type, consecutive_count=0)
        db.add(tracker)
        db.flush()
        return tracker

    def record_evaluation(
        self,
        db: Session,
        plant_id: int,
        anomaly_type: str,
        is_crossing: bool,
        value: Optional[float] = None,
    ) -> AnomalyTracker:
        """
        Advance the debounce streak for one evaluation.

        - is_crossing=True  -> consecutive_count += 1
        - is_crossing=False -> consecutive_count reset to 0 (a single clean
          reading clears the streak; this is what makes the detector
          "debounced" rather than just a higher static threshold)

        Does not decide whether to raise a PlantAnomaly — that comparison
        against config.ANOMALY_DEBOUNCE_COUNT is AnomalyService's job.
        Caller (a pipeline service) must not commit; this only flushes.
        """
        tracker = self.get_or_create(db, plant_id, anomaly_type)
        tracker.consecutive_count = tracker.consecutive_count + 1 if is_crossing else 0
        tracker.last_evaluated_at = datetime.utcnow()
        if value is not None:
            tracker.last_value = value
        db.flush()
        return tracker

    def mark_triggered(self, db: Session, tracker: AnomalyTracker) -> AnomalyTracker:
        """
        Call once a PlantAnomaly has actually been created from this
        tracker's streak. Resets the streak so the next PlantAnomaly for
        this (plant_id, anomaly_type) requires a fresh run of consecutive
        crossings, instead of firing again on every subsequent evaluation
        while the condition remains bad.
        """
        tracker.last_triggered_at = datetime.utcnow()
        tracker.consecutive_count = 0
        db.flush()
        return tracker


anomaly_tracker_repository = AnomalyTrackerRepository()
