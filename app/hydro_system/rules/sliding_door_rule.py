# app/hydro_system/rules/sliding_door_rule.py

from .base_rule import ActuatorRule
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class SlidingDoorRule(ActuatorRule):
    """
    Sliding doors are manually/command-driven (up / stop / down), not
    sensor-automated like fans or pumps. This rule intentionally never
    triggers automatically — control happens via explicit up/down (control_actuator_by_id) and
    stop (stop_actuator_by_id) commands in actuator_controller.py.
    """

    actuator_type = "sliding_door"

    def should_activate(
        self,
        sensor_data: dict,
        thresholds: dict,
        actuator=None
    ) -> bool:
        return False