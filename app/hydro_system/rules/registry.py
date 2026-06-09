# app/hydro_system/rules/registry.py

from typing import Dict
from .base_rule import ActuatorRule

_rules: Dict[str, ActuatorRule] = {}


def register_rule(rule: ActuatorRule) -> None:
    _rules[rule.actuator_type] = rule


def get_rule(actuator_type: str) -> ActuatorRule | None:
    return _rules.get(actuator_type)


def get_all_rules() -> Dict[str, ActuatorRule]:
    return _rules