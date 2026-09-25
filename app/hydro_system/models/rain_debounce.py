# app/hydro_system/models/rain_debounce.py
#
# Debounce state for the rain sensor, one row per device.
#
# Problem: a single (possibly stuck/miscalibrated) rain_detected=True
# reading currently forces every water-related actuator (pump, water_pump,
# valve, nutrient_pump) OFF immediately via the rain branch in
# rules_engine.check_rules(), overriding manual and scheduled control. A
# momentary noisy reading -- or a permanently stuck sensor -- can silently
# kill irrigation with no warning.
#
# This table makes rain detection debounced (Schmitt-trigger style): the
# *effective* rain state used by the rule engine only flips once N
# consecutive readings disagree with the current effective state (see
# services/rain_debounce_service.py). A single stray reading no longer
# changes actuator behavior in either direction.
#
# Lives in its own table (not in-memory) so the streak survives process
# restarts and stays correct across scheduler workers -- same rationale as
# app/ai_vision/models/anomaly_tracker.py.

from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint, func
from app.database import Base


class RainSensorDebounceState(Base):
    __tablename__ = "hydro_rain_debounce_state"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices_hydro.id"), nullable=False, unique=True, index=True)

    # The debounced/confirmed rain state actually used by the rule engine.
    effective_rain_detected = Column(Boolean, nullable=False, default=False)

    # How many consecutive readings have disagreed with effective_rain_detected.
    consecutive_count = Column(Integer, nullable=False, default=0)

    # Last raw reading seen, kept for debugging/visibility.
    last_raw_rain_detected = Column(Boolean, nullable=True)

    last_evaluated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("device_id", name="uq_rain_debounce_device"),
    )

    def __repr__(self):
        return (
            f"<RainSensorDebounceState(device_id={self.device_id}, "
            f"effective={self.effective_rain_detected}, streak={self.consecutive_count})>"
        )
