from typing import Optional
from app.hydro_system import sensors, device_controller as controller, state_manager
from app.hydro_system.scheduler import start_sensor_job, stop_sensor_job, restart_sensor_job
from app.hydro_system.rules_engine import check_rules
from app.hydro_system.config import DEFAULT_THRESHOLDS
from app.hydro_system.services.device_service import hydro_device_service
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

# def control_pump(on: bool, user_id: int, device_id: Optional[int] = None):
#     """Control irrigation pump"""
#     if on:
#         controller.turn_pump_on()
#     else:
#         controller.turn_pump_off()
#     state_manager.set_state("pump", on)
#     logger.info(f"Irrigation pump {'ON' if on else 'OFF'}")

# def control_light(on: bool):
#     """Control grow lights"""
#     if on:
#         controller.turn_light_on()
#     else:
#         controller.turn_light_off()
#     state_manager.set_state("light", on)
#     logger.info(f"Grow lights {'ON' if on else 'OFF'}")

# def control_fan(on: bool):
#     """Control ventilation fan"""
#     if on:
#         controller.turn_fan_on()
#     else:
#         controller.turn_fan_off()
#     state_manager.set_state("fan", on)
#     logger.info(f"Ventilation fan {'ON' if on else 'OFF'}")

# def control_water_pump(on: bool):
#     """Control water tank refill pump"""
#     if on:
#         controller.turn_water_pump_on()
#     else:
#         controller.turn_water_pump_off()
#     state_manager.set_state("water_pump", on)
#     logger.info(f"Water refill pump {'ON' if on else 'OFF'}")

# def refill_water_tank(duration_seconds: int = 300):
#     """Refill water tank for specified duration (default 5 minutes)"""
#     logger.info(f"Starting water tank refill for {duration_seconds} seconds")
#     control_water_pump(True)
    
#     # In a real implementation, you would set a timer to turn off the pump
#     # For now, we'll just log the action
#     return {
#         "message": f"Water tank refill started for {duration_seconds} seconds",
#         "duration": duration_seconds,
#         "status": "running"
#     }

# def emergency_stop():
#     """Emergency stop all devices"""
#     logger.warning("EMERGENCY STOP activated - turning off all devices")
#     control_pump(False)
#     control_light(False)
#     control_fan(False)
#     control_water_pump(False)
    
#     return {
#         "message": "Emergency stop activated - all devices turned off",
#         "timestamp": "now",
#         "devices_stopped": ["pump", "light", "fan", "water_pump"]
#     }

def control_pump(on: bool, user_id: int, device_id: Optional[int] = None):
    """Control irrigation pump for specific user/device"""
    if device_id:
        device = hydro_device_service.get_device_for_user(device_id, user_id)
        if not device or device.type != "pump":
            raise ValueError("Pump device not found or not authorized")
        controller.turn_pump_on() if on else controller.turn_pump_off()
        state_manager.set_state(f"pump_{device_id}", on)
        logger.info(f"User {user_id} - Pump {device_id} {'ON' if on else 'OFF'}")
    else:
        controller.turn_pump_on() if on else controller.turn_pump_off()
        state_manager.set_state("pump", on)
        logger.info(f"Irrigation pump {'ON' if on else 'OFF'}")

def control_light(on: bool, user_id: int, device_id: Optional[int] = None):
    """Control grow lights"""
    if device_id:
        device = hydro_device_service.get_device_for_user(device_id, user_id)
        if not device or device.type != "light":
            raise ValueError("Light device not found or not authorized")
        controller.turn_light_on() if on else controller.turn_light_off()
        state_manager.set_state(f"light_{device_id}", on)
        logger.info(f"User {user_id} - Light {device_id} {'ON' if on else 'OFF'}")
    else:
        controller.turn_light_on() if on else controller.turn_light_off()
        state_manager.set_state("light", on)
        logger.info(f"Grow lights {'ON' if on else 'OFF'}")

def control_fan(on: bool, user_id: int, device_id: Optional[int] = None):
    """Control ventilation fan"""
    if device_id:
        device = hydro_device_service.get_device_for_user(device_id, user_id)
        if not device or device.type != "fan":
            raise ValueError("Fan device not found or not authorized")
        controller.turn_fan_on() if on else controller.turn_fan_off()
        state_manager.set_state(f"fan_{device_id}", on)
        logger.info(f"User {user_id} - Fan {device_id} {'ON' if on else 'OFF'}")
    else:
        controller.turn_fan_on() if on else controller.turn_fan_off()
        state_manager.set_state("fan", on)
        logger.info(f"Ventilation fan {'ON' if on else 'OFF'}")

def control_water_pump(on: bool, user_id: int, device_id: Optional[int] = None):
    """Control water tank refill pump"""
    if device_id:
        device = hydro_device_service.get_device_for_user(device_id, user_id)
        if not device or device.type != "water_pump":
            raise ValueError("Water pump device not found or not authorized")
        controller.turn_water_pump_on() if on else controller.turn_water_pump_off()
        state_manager.set_state(f"water_pump_{device_id}", on)
        logger.info(f"User {user_id} - Water pump {device_id} {'ON' if on else 'OFF'}")
    else:
        controller.turn_water_pump_on() if on else controller.turn_water_pump_off()
        state_manager.set_state("water_pump", on)
        logger.info(f"Water refill pump {'ON' if on else 'OFF'}")

def refill_water_tank(user_id: int, device_id: Optional[int] = None, duration_seconds: int = 300):
    """Refill water tank for specified duration"""
    logger.info(f"User {user_id} - Starting water tank refill for {duration_seconds} seconds on device {device_id or 'default'}")
    control_water_pump(True, user_id, device_id)

    # In production: schedule auto-shutdown
    return {
        "message": f"Water tank refill started for {duration_seconds} seconds",
        "duration": duration_seconds,
        "status": "running",
        "device_id": device_id
    }

def emergency_stop(user_id: int):
    """Emergency stop all devices for the user"""
    logger.warning(f"EMERGENCY STOP activated for user {user_id} - turning off all devices")
    devices = hydro_device_service.get_devices_by_user(user_id)
    
    for device in devices:
        try:
            if device.type == "pump":
                control_pump(False, user_id, device.id)
            elif device.type == "light":
                control_light(False, user_id, device.id)
            elif device.type == "fan":
                control_fan(False, user_id, device.id)
            elif device.type == "water_pump":
                control_water_pump(False, user_id, device.id)
        except Exception as e:
            logger.warning(f"Failed to stop device {device.id}: {e}")

    return {
        "message": f"Emergency stop completed for user {user_id}",
        "devices_stopped": [d.id for d in devices]
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
