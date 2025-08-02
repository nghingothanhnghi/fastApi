# File: app/hydro_system/rules_engine.py
# Description: Rules engine to determine actions based on sensor data

from app.hydro_system.config import DEFAULT_THRESHOLDS
from app.hydro_system.models.actuator import HydroActuator
import logging

logger = logging.getLogger(__name__)

def should_turn_on_pump(sensor_data: dict, thresholds: dict) -> bool:
    """Check if irrigation pump should be turned on based on soil moisture"""
    moisture = sensor_data.get("moisture", 0)
    water_level = sensor_data.get("water_level", 0)
    
    # Don't turn on pump if water level is too low
    if water_level < thresholds.get("water_level_min", 20):
        logger.warning(f"Cannot turn on pump: Water level too low ({water_level}%)")
        return False
    
    return moisture < thresholds.get("moisture_min", 30)

def should_turn_on_light(sensor_data: dict, thresholds: dict) -> bool:
    """Check if grow lights should be turned on based on light intensity"""
    light = sensor_data.get("light", 0)
    return light < thresholds.get("light_min", 300)

def should_turn_on_fan(sensor_data: dict, thresholds: dict) -> bool:
    """Check if ventilation fan should be turned on based on temperature"""
    temperature = sensor_data.get("temperature", 0)
    return temperature > thresholds.get("temperature_max", 28)

def should_refill_water_tank(sensor_data: dict, thresholds: dict) -> bool:
    """Check if water tank needs refilling"""
    water_level = sensor_data.get("water_level", 0)
    return water_level < thresholds.get("water_level_min", 20)

def is_water_level_critical(sensor_data: dict, thresholds: dict) -> bool:
    """Check if water level is critically low (emergency alert)"""
    water_level = sensor_data.get("water_level", 0)
    return water_level < thresholds.get("water_level_critical", 10)

def get_water_level_status(sensor_data: dict, thresholds: dict) -> dict:
    """Get detailed water level status and recommendations"""
    water_level = sensor_data.get("water_level", 0)
    
    if water_level < thresholds.get("water_level_critical", 10):
        status = "critical"
        message = "CRITICAL: Water level extremely low! Immediate refill required."
        priority = "high"
    elif water_level < thresholds.get("water_level_min", 20):
        status = "low"
        message = "Water level low. Refill recommended."
        priority = "medium"
    elif water_level > 80:
        status = "optimal"
        message = "Water level optimal."
        priority = "low"
    else:
        status = "adequate"
        message = "Water level adequate."
        priority = "low"
    
    return {
        "status": status,
        "message": message,
        "priority": priority,
        "current_level": water_level,
        "min_threshold": thresholds.get("water_level_min", 20),
        "critical_threshold": thresholds.get("water_level_critical", 10)
    }

def should_turn_on_water_pump(sensor_data: dict, thresholds: dict) -> bool:
    """
    Determine if the water pump should be turned on.
    Example logic: used to refill internal reservoirs when main tank is sufficient
    """
    water_level = sensor_data.get("water_level", 0)
    return water_level > thresholds.get("water_level_min", 20)  # Example: pump if water is available

def should_open_valve(sensor_data: dict, thresholds: dict) -> bool:
    """
    Determine if a valve should be opened.
    Example logic: open valve if soil is dry and water level is sufficient
    """
    moisture = sensor_data.get("moisture", 0)
    water_level = sensor_data.get("water_level", 0)

    if water_level < thresholds.get("water_level_min", 20):
        logger.warning("Cannot open valve: Water level too low")
        return False

    return moisture < thresholds.get("moisture_min", 30)


# def check_rules(
#     sensor_data: dict,
#     thresholds: dict = DEFAULT_THRESHOLDS,
#     actuators: list = []
# ) -> dict:
#     """
#     Evaluate sensor data and decide actions for each actuator, using individual thresholds if available.
#     Returns a list of per-actuator actions and system alerts.
#     """
#     actions = []
#     alerts = []

#     for actuator in actuators:
#         actuator_type = actuator.type.lower()
#         actuator_id = actuator.id
#         # ✅ Get thresholds from the associated device
#         actuator_thresholds = getattr(actuator.device, "thresholds", {}) or thresholds

#         should_activate = False

#         if actuator_type == "pump":
#             should_activate = should_turn_on_pump(sensor_data, actuator_thresholds)
#         elif actuator_type == "light":
#             should_activate = should_turn_on_light(sensor_data, actuator_thresholds)
#         elif actuator_type == "fan":
#             should_activate = should_turn_on_fan(sensor_data, actuator_thresholds)
#         elif actuator_type == "valve":
#             should_activate = should_open_valve(sensor_data, actuator_thresholds)
#         elif actuator_type == "water_pump":
#             should_activate = should_turn_on_water_pump(sensor_data, actuator_thresholds)
#         # Add more actuator types as needed...

#         actions.append({
#             "actuator_id": actuator_id,
#             "on": should_activate,
#             "type": actuator_type,
#             "thresholds_used": actuator_thresholds
#         })

#     # Evaluate general system alerts (global threshold)
#     if is_water_level_critical(sensor_data, thresholds):
#         alerts.append({
#             "type": "critical",
#             "message": "Water level critically low!",
#             "sensor": "water_level",
#             "value": sensor_data.get("water_level", 0),
#             "action_required": "Immediate water tank refill"
#         })
#     elif should_refill_water_tank(sensor_data, thresholds):
#         alerts.append({
#             "type": "warning",
#             "message": "Water level low",
#             "sensor": "water_level",
#             "value": sensor_data.get("water_level", 0),
#             "action_required": "Schedule water tank refill"
#         })

#     # Compound condition alert
#     if sensor_data.get("moisture", 0) < thresholds.get("moisture_min", 30) and \
#        sensor_data.get("water_level", 0) < thresholds.get("water_level_min", 20):
#         alerts.append({
#             "type": "warning",
#             "message": "Cannot irrigate: Both soil moisture and water level are low",
#             "sensor": "moisture_water_level",
#             "action_required": "Refill water tank before irrigation"
#         })

#     return {
#         "actions": actions,
#         "alerts": alerts,
#         "water_status": get_water_level_status(sensor_data, thresholds)
#     }


def check_rules(
    sensor_data: dict,
    thresholds: dict = DEFAULT_THRESHOLDS,
    actuators: list = [],
    overrides: dict = None,
) -> dict:
    """
    Evaluate sensor data and decide actions for each actuator, using individual thresholds if available.
    Optionally override global thresholds with `overrides`.
    Returns a list of per-actuator actions and system alerts.
    """
    actions = []
    alerts = []

    # Merge overrides into thresholds if provided
    if overrides:
        thresholds = {**thresholds, **overrides}

    for actuator in actuators:
        actuator_type = actuator.type.lower()
        actuator_id = actuator.id

        # Get thresholds from device or fall back to global thresholds (already merged with overrides)
        actuator_thresholds = getattr(actuator.device, "thresholds", {}) or thresholds

        should_activate = False

        if actuator_type == "pump":
            should_activate = should_turn_on_pump(sensor_data, actuator_thresholds)
        elif actuator_type == "light":
            should_activate = should_turn_on_light(sensor_data, actuator_thresholds)
        elif actuator_type == "fan":
            should_activate = should_turn_on_fan(sensor_data, actuator_thresholds)
        elif actuator_type == "valve":
            should_activate = should_open_valve(sensor_data, actuator_thresholds)
        elif actuator_type == "water_pump":
            should_activate = should_turn_on_water_pump(sensor_data, actuator_thresholds)

        actions.append({
            "actuator_id": actuator_id,
            "on": should_activate,
            "type": actuator_type,
            "thresholds_used": actuator_thresholds
        })

    # Global/system alerts (based on possibly overridden thresholds)
    if is_water_level_critical(sensor_data, thresholds):
        alerts.append({
            "type": "critical",
            "message": "Water level critically low!",
            "sensor": "water_level",
            "value": sensor_data.get("water_level", 0),
            "action_required": "Immediate water tank refill"
        })
    elif should_refill_water_tank(sensor_data, thresholds):
        alerts.append({
            "type": "warning",
            "message": "Water level low",
            "sensor": "water_level",
            "value": sensor_data.get("water_level", 0),
            "action_required": "Schedule water tank refill"
        })

    # Compound alert
    if sensor_data.get("moisture", 0) < thresholds.get("moisture_min", 30) and \
       sensor_data.get("water_level", 0) < thresholds.get("water_level_min", 20):
        alerts.append({
            "type": "warning",
            "message": "Cannot irrigate: Both soil moisture and water level are low",
            "sensor": "moisture_water_level",
            "action_required": "Refill water tank before irrigation"
        })

    return {
        "actions": actions,
        "alerts": alerts,
        "water_status": get_water_level_status(sensor_data, thresholds)
    }


