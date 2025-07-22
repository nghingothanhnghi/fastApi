from app.hydro_system import sensors, device_controller as controller, state_manager
from app.hydro_system.scheduler import start_sensor_job, stop_sensor_job, restart_sensor_job
from app.hydro_system.rules_engine import check_rules
from app.hydro_system.config import DEFAULT_THRESHOLDS
import logging

logger = logging.getLogger(__name__)

def get_system_status():
    """Get comprehensive system status including all sensors and devices"""
    sensor_data = sensors.read_sensors()
    rules_result = check_rules(sensor_data, DEFAULT_THRESHOLDS)
    
    return {
        "sensors": sensor_data,
        "devices": {
            "pump_state": state_manager.get_state("pump"),
            "light_state": state_manager.get_state("light"),
            "fan_state": state_manager.get_state("fan"),
            "water_pump_state": state_manager.get_state("water_pump")
        },
        "system": {
            "scheduler_state": state_manager.get_state("scheduler")
        },
        "automation": {
            "rules_result": rules_result,
            "thresholds": DEFAULT_THRESHOLDS
        }
    }

def control_pump(on: bool):
    """Control irrigation pump"""
    if on:
        controller.turn_pump_on()
    else:
        controller.turn_pump_off()
    state_manager.set_state("pump", on)
    logger.info(f"Irrigation pump {'ON' if on else 'OFF'}")

def control_light(on: bool):
    """Control grow lights"""
    if on:
        controller.turn_light_on()
    else:
        controller.turn_light_off()
    state_manager.set_state("light", on)
    logger.info(f"Grow lights {'ON' if on else 'OFF'}")

def control_fan(on: bool):
    """Control ventilation fan"""
    if on:
        controller.turn_fan_on()
    else:
        controller.turn_fan_off()
    state_manager.set_state("fan", on)
    logger.info(f"Ventilation fan {'ON' if on else 'OFF'}")

def control_water_pump(on: bool):
    """Control water tank refill pump"""
    if on:
        controller.turn_water_pump_on()
    else:
        controller.turn_water_pump_off()
    state_manager.set_state("water_pump", on)
    logger.info(f"Water refill pump {'ON' if on else 'OFF'}")

def refill_water_tank(duration_seconds: int = 300):
    """Refill water tank for specified duration (default 5 minutes)"""
    logger.info(f"Starting water tank refill for {duration_seconds} seconds")
    control_water_pump(True)
    
    # In a real implementation, you would set a timer to turn off the pump
    # For now, we'll just log the action
    return {
        "message": f"Water tank refill started for {duration_seconds} seconds",
        "duration": duration_seconds,
        "status": "running"
    }

def emergency_stop():
    """Emergency stop all devices"""
    logger.warning("EMERGENCY STOP activated - turning off all devices")
    control_pump(False)
    control_light(False)
    control_fan(False)
    control_water_pump(False)
    
    return {
        "message": "Emergency stop activated - all devices turned off",
        "timestamp": "now",
        "devices_stopped": ["pump", "light", "fan", "water_pump"]
    }

def scheduler_control(action: str):
    """Control the sensor data collection scheduler"""
    if action == "start":
        start_sensor_job()
    elif action == "stop":
        stop_sensor_job()
    elif action == "restart":
        restart_sensor_job()
    
    logger.info(f"Scheduler {action} command executed")
