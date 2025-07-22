# File: app/hydro_system/rules_engine.py

from app.hydro_system.config import DEFAULT_THRESHOLDS
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

def check_rules(sensor_data: dict, thresholds: dict = DEFAULT_THRESHOLDS) -> dict:
    """
    Check sensor values against rules and return a dict of actions and alerts.
    """
    actions = {
        "pump": should_turn_on_pump(sensor_data, thresholds),
        "light": should_turn_on_light(sensor_data, thresholds),
        "fan": should_turn_on_fan(sensor_data, thresholds),
        "water_refill": should_refill_water_tank(sensor_data, thresholds)
    }
    
    alerts = []
    
    # Check for water level alerts
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
    
    # Check for other sensor alerts
    moisture = sensor_data.get("moisture", 0)
    if moisture < thresholds.get("moisture_min", 30) and sensor_data.get("water_level", 0) < thresholds.get("water_level_min", 20):
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
