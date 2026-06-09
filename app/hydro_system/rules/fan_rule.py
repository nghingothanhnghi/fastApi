# app/hydro_system/rules/fan_rule.py

from .base_rule import ActuatorRule


class FanRule(ActuatorRule):

    actuator_type = "fan"

    def should_activate(
        self,
        sensor_data: dict,
        thresholds: dict,
        actuator=None
    ) -> bool:

        temperature = sensor_data.get("temperature", 0)

        return temperature > thresholds.get(
            "temperature_max",
            28
        )