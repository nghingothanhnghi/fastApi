# app/hydro_system/rules/base_rule.py

from abc import ABC, abstractmethod


class ActuatorRule(ABC):
    actuator_type: str

    @abstractmethod
    def should_activate(
        self,
        sensor_data: dict,
        thresholds: dict,
        actuator=None
    ) -> bool:
        pass