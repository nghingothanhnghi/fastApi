# app/hydro_system/rules/light_rule.py

from .base_rule import ActuatorRule


class LightRule(ActuatorRule):

    actuator_type = "light"

    def should_activate(
        self,
        sensor_data: dict,
        thresholds: dict,
        actuator=None
    ) -> bool:

        light = sensor_data.get("light", 0)

        return light < thresholds.get(
            "light_min",
            300
        )