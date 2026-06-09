# app/hydro_system/rules/water_pump_rule.py

from .base_rule import ActuatorRule


class WaterPumpRule(ActuatorRule):

    actuator_type = "water_pump"

    def should_activate(
        self,
        sensor_data: dict,
        thresholds: dict,
        actuator=None
    ) -> bool:

        return False