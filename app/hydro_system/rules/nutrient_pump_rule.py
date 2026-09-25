# app/hydro_system/rules/nutrient_pump_rule.py

from .base_rule import ActuatorRule
from app.hydro_system.helpers.comparision_helper import safe_lt, safe_gt

class NutrientPumpRule(ActuatorRule):

    actuator_type = "nutrient_pump"

    def should_activate(
        self,
        sensor_data: dict,
        thresholds: dict,
        actuator=None
    ) -> bool:

        ec = sensor_data.get("ec")
        ppm = sensor_data.get("ppm")

        if safe_gt(ec, 0):
            return safe_lt(ec, thresholds.get("ec_min", 1.2))

        if safe_gt(ppm, 0):
            return safe_lt(ppm, thresholds.get("ppm_min", 600))

        return False        