# app/hydro_system/rules/valve_rule.py

from .base_rule import ActuatorRule
from app.hydro_system.helpers.comparision_helper import safe_lt
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class ValveRule(ActuatorRule):

    actuator_type = "valve"

    def should_activate(
        self,
        sensor_data: dict,
        thresholds: dict,
        actuator=None
    ) -> bool:

        moisture = sensor_data.get("moisture")
        water_level = sensor_data.get("water_level")

        if safe_lt(water_level, thresholds.get("water_level_min", 20)):
            logger.warning("Cannot open valve: Water level too low")
            return False

        return safe_lt(moisture, thresholds.get("moisture_min", 30))        