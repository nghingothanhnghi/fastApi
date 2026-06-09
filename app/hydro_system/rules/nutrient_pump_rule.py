# app/hydro_system/rules/nutrient_pump_rule.py

from .base_rule import ActuatorRule


class NutrientPumpRule(ActuatorRule):

    actuator_type = "nutrient_pump"

    def should_activate(
        self,
        sensor_data: dict,
        thresholds: dict,
        actuator=None
    ) -> bool:

        ec = sensor_data.get("ec", 0)
        ppm = sensor_data.get("ppm", 0)

        if ec > 0:
            return ec < thresholds.get(
                "ec_min",
                1.2
            )

        if ppm > 0:
            return ppm < thresholds.get(
                "ppm_min",
                600
            )

        return False