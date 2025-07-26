# File: backend/app/hydro_system/device_controller.py
# Description: Hardware control logic for hydroponic system devices

from app.hydro_system.rules_engine import check_rules
from app.hydro_system.state_manager import set_state, get_state
from app.hydro_system.config import DEVICE_IDS
import logging

logger = logging.getLogger(__name__)

# Irrigation Pump Control
def turn_pump_on():
    """Turn on irrigation pump"""
    device_id = DEVICE_IDS.get("pump", "device_pump_001")
    logger.info(f"Turning ON irrigation pump: {device_id}")
    # In production, this would interface with actual hardware
    # Example: GPIO.output(PUMP_PIN, GPIO.HIGH)
    print(f"✅ Irrigation pump ({device_id}) turned ON")

def turn_pump_off():
    """Turn off irrigation pump"""
    device_id = DEVICE_IDS.get("pump", "device_pump_001")
    logger.info(f"Turning OFF irrigation pump: {device_id}")
    # In production, this would interface with actual hardware
    # Example: GPIO.output(PUMP_PIN, GPIO.LOW)
    print(f"❌ Irrigation pump ({device_id}) turned OFF")

# Grow Light Control
def turn_light_on():
    """Turn on grow lights"""
    device_id = DEVICE_IDS.get("light", "device_light_001")
    logger.info(f"Turning ON grow lights: {device_id}")
    # In production, this would interface with actual hardware
    print(f"💡 Grow lights ({device_id}) turned ON")

def turn_light_off():
    """Turn off grow lights"""
    device_id = DEVICE_IDS.get("light", "device_light_001")
    logger.info(f"Turning OFF grow lights: {device_id}")
    # In production, this would interface with actual hardware
    print(f"🌙 Grow lights ({device_id}) turned OFF")

# Ventilation Fan Control
def turn_fan_on():
    """Turn on ventilation fan"""
    device_id = DEVICE_IDS.get("fan", "device_fan_001")
    logger.info(f"Turning ON ventilation fan: {device_id}")
    # In production, this would interface with actual hardware
    print(f"🌪️ Ventilation fan ({device_id}) turned ON")

def turn_fan_off():
    """Turn off ventilation fan"""
    device_id = DEVICE_IDS.get("fan", "device_fan_001")
    logger.info(f"Turning OFF ventilation fan: {device_id}")
    # In production, this would interface with actual hardware
    print(f"🔇 Ventilation fan ({device_id}) turned OFF")

# Water Tank Refill Pump Control
def turn_water_pump_on():
    """Turn on water tank refill pump"""
    device_id = DEVICE_IDS.get("water_pump", "device_water_pump_001")
    logger.info(f"Turning ON water refill pump: {device_id}")
    # In production, this would interface with actual hardware
    print(f"💧 Water refill pump ({device_id}) turned ON")

def turn_water_pump_off():
    """Turn off water tank refill pump"""
    device_id = DEVICE_IDS.get("water_pump", "device_water_pump_001")
    logger.info(f"Turning OFF water refill pump: {device_id}")
    # In production, this would interface with actual hardware
    print(f"🚰 Water refill pump ({device_id}) turned OFF")

# Valve Control
def open_valve():
    """Open water flow valve"""
    device_id = DEVICE_IDS.get("valve", "device_valve_001")
    logger.info(f"Opening valve: {device_id}")
    print(f"🔓 Valve ({device_id}) OPENED")

def close_valve():
    """Close water flow valve"""
    device_id = DEVICE_IDS.get("valve", "device_valve_001")
    logger.info(f"Closing valve: {device_id}")
    print(f"🔒 Valve ({device_id}) CLOSED")

def handle_automation(sensor_data):
    """Handle automated device control based on sensor data"""
    rules_result = check_rules(sensor_data)
    actions = rules_result.get("actions", {})
    alerts = rules_result.get("alerts", [])
    
    # Log any alerts
    for alert in alerts:
        if alert["type"] == "critical":
            logger.critical(f"CRITICAL ALERT: {alert['message']}")
        elif alert["type"] == "warning":
            logger.warning(f"WARNING: {alert['message']}")
    
    # Execute automation actions
    for device, should_activate in actions.items():
        prev_state = get_state(device)
        
        if should_activate != prev_state:
            set_state(device, should_activate)

            if device == "pump":
                turn_pump_on() if should_activate else turn_pump_off()
            elif device == "light":
                turn_light_on() if should_activate else turn_light_off()
            elif device == "fan":
                turn_fan_on() if should_activate else turn_fan_off()
            elif device == "water_refill":
                logger.warning("Water refill needed - manual intervention required")

            logger.info(f"[Automation] {device}: {should_activate}")
    
    return {
        "actions_taken": actions,
        "alerts": alerts,
        "sensor_data": sensor_data
    }

