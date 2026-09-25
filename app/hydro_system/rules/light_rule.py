# app/hydro_system/rules/light_rule.py

from .base_rule import ActuatorRule
from app.hydro_system.helpers.comparision_helper import safe_lt

class LightRule(ActuatorRule):

    actuator_type = "light"

    def should_activate(
        self,
        sensor_data: dict,
        thresholds: dict,
        actuator=None
    ) -> bool:

        light = sensor_data.get("light")

        return safe_lt(light, thresholds.get("light_min", 300))        