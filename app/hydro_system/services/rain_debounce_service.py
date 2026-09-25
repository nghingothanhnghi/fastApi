# app/hydro_system/services/rain_debounce_service.py
#
# Debounces the raw rain_detected boolean per device before it's allowed to
# influence actuator control in rules_engine.check_rules(). See
# app/hydro_system/models/rain_debounce.py for the "why".

from typing import Optional
from sqlalchemy.orm import Session

from app.hydro_system.models.rain_debounce import RainSensorDebounceState
from app.hydro_system.config import RAIN_DEBOUNCE_COUNT
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class RainDebounceService:

    def _get_or_create(self, db: Session, device_id: int) -> RainSensorDebounceState:
        tracker = (
            db.query(RainSensorDebounceState)
            .filter(RainSensorDebounceState.device_id == device_id)
            .first()
        )
        if tracker:
            return tracker

        tracker = RainSensorDebounceState(
            device_id=device_id,
            effective_rain_detected=False,
            consecutive_count=0,
        )
        db.add(tracker)
        db.commit()
        db.refresh(tracker)
        return tracker

    def get_effective_rain_state(
        self,
        db: Session,
        device_id: Optional[int],
        raw_rain_detected: bool,
        debounce_count: int = RAIN_DEBOUNCE_COUNT,
    ) -> bool:
        """
        Returns the debounced rain state to actually use for control
        decisions. The effective state only flips once `debounce_count`
        consecutive readings disagree with it - a lone stray True (or
        False) reading changes nothing, in either direction.

        Without a device_id (e.g. an ad-hoc/manual call with no device
        context) debounce can't be tracked per-device, so the raw reading
        is returned unchanged rather than silently pretending to debounce.
        """
        if device_id is None:
            return raw_rain_detected

        try:
            tracker = self._get_or_create(db, device_id)

            if raw_rain_detected == tracker.effective_rain_detected:
                # Reading confirms the current effective state - any
                # opposite-direction streak stops building.
                if tracker.consecutive_count != 0:
                    tracker.consecutive_count = 0
            else:
                tracker.consecutive_count += 1
                if tracker.consecutive_count >= debounce_count:
                    logger.info(
                        f"[RainDebounce] device={device_id} flipping effective "
                        f"rain_detected {tracker.effective_rain_detected} -> "
                        f"{raw_rain_detected} after {tracker.consecutive_count} "
                        f"consecutive disagreeing readings"
                    )
                    tracker.effective_rain_detected = raw_rain_detected
                    tracker.consecutive_count = 0

            tracker.last_raw_rain_detected = raw_rain_detected
            db.commit()
            db.refresh(tracker)
            return tracker.effective_rain_detected

        except Exception as e:
            logger.error(f"[RainDebounce] Failed to evaluate debounce for device {device_id}: {e}")
            db.rollback()
            # Fail safe toward the previous confirmed state rather than
            # trusting a single unvalidated raw reading.
            return raw_rain_detected


rain_debounce_service = RainDebounceService()
