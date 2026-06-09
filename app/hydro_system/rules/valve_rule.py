# app/hydro_system/rules/valve_rule.py

from .base_rule import ActuatorRule
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

        moisture = sensor_data.get("moisture", 0)
        water_level = sensor_data.get("water_level", 0)

        if water_level < thresholds.get(
            "water_level_min",
            20
        ):
            logger.warning(
                "Cannot open valve: Water level too low"
            )
            return False

        return moisture < thresholds.get(
            "moisture_min",
            30
        )