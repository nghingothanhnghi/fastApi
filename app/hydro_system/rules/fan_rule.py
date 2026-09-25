# app/hydro_system/rules/fan_rule.py

from .base_rule import ActuatorRule
from app.hydro_system.helpers.comparision_helper import safe_gt

class FanRule(ActuatorRule):

    actuator_type = "fan"

    def should_activate(
        self,
        sensor_data: dict,
        thresholds: dict,
        actuator=None
    ) -> bool:

        temperature = sensor_data.get("temperature")

        return safe_gt(temperature, thresholds.get("temperature_max", 28))        