# app/hydro_system/rules/__init__.py

from .registry import register_rule

from .pump_rule import PumpRule
from .light_rule import LightRule
from .fan_rule import FanRule
from .valve_rule import ValveRule
from .water_pump_rule import WaterPumpRule
from .nutrient_pump_rule import NutrientPumpRule


register_rule(PumpRule())
register_rule(LightRule())
register_rule(FanRule())
register_rule(ValveRule())
register_rule(WaterPumpRule())
register_rule(NutrientPumpRule())