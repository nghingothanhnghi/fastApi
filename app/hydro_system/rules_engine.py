# File: app/hydro_system/rules_engine.py

from app.hydro_system.config import DEFAULT_THRESHOLDS

def should_turn_on_pump(sensor_data: dict, thresholds: dict) -> bool:
    moisture = sensor_data.get("moisture", 0)
    return moisture < thresholds.get("moisture_min", 30)

def should_turn_on_light(sensor_data: dict, thresholds: dict) -> bool:
    light = sensor_data.get("light", 0)
    return light < thresholds.get("light_min", 300)

def should_turn_on_fan(sensor_data: dict, thresholds: dict) -> bool:
    temperature = sensor_data.get("temperature", 0)
    return temperature > thresholds.get("temperature_max", 28)

# ✅ Add this function:
def check_rules(sensor_data: dict, thresholds: dict = DEFAULT_THRESHOLDS) -> dict:
    """
    Check sensor values against rules and return a dict of actions.
    """
    return {
        "pump": should_turn_on_pump(sensor_data, thresholds),
        "light": should_turn_on_light(sensor_data, thresholds),
        "fan": should_turn_on_fan(sensor_data, thresholds),
    }
