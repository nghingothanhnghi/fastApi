# app/hydro_system/controllers/hydro_system_controller.py
# Defines endpoints for controlling individual devices (pump, light, fan, water pump)
from fastapi import HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from app.hydro_system import sensors, state_manager
from app.hydro_system.controllers import actuator_controller
from app.hydro_system.scheduler import start_sensor_job, stop_sensor_job, restart_sensor_job
from app.hydro_system.rules_engine import check_rules
from app.hydro_system.config import DEFAULT_THRESHOLDS
from app.hydro_system.services.device_service import hydro_device_service
from app.hydro_system.services.actuator_service import hydro_actuator_service
import logging

logger = logging.getLogger(__name__)

def get_system_status(db: Session, user_id: Optional[int] = None, device_id: Optional[int] = None):
    devices = []

    if device_id:
        device = hydro_device_service.get_device_for_user(db, device_id, user_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found or not authorized")
        devices = [device]
    elif user_id:
        devices = hydro_device_service.get_devices_by_user(db, user_id)
        if not devices:
            raise HTTPException(status_code=404, detail="No devices found for this user")
    else:
        raise HTTPException(status_code=400, detail="Must provide user_id or device_id to retrieve system status")

    results = []

    for device in devices:
        sensor_data = sensors.read_sensors(device_id=device.id)
        thresholds = device.thresholds if hasattr(device, "thresholds") and device.thresholds else DEFAULT_THRESHOLDS
        rules_result = check_rules(sensor_data, thresholds)

        actuators = hydro_actuator_service.get_actuators_by_device(db, device.id)

        actuators_state = []

        for actuator in actuators:
            sensor_value = None
            if actuator.sensor_key and actuator.sensor_key in sensor_data:
                sensor_value = sensor_data[actuator.sensor_key]

            actuators_state.append({
                "id": actuator.id,
                "name": actuator.name,
                "type": actuator.type,
                "pin": actuator.pin,
                "port": actuator.port,
                "is_active": actuator.is_active,
                "default_state": actuator.default_state,
                "sensor_key": actuator.sensor_key,
                "linked_sensor_value": sensor_value,
                "current_state": state_manager.get_state(f"{actuator.type}_{actuator.device_id}_{actuator.port}")
            })      

        results.append({
            "device_id": device.id,
            "device_name": device.name,
            "location": device.location,
            "sensors": sensor_data,
            "actuators": actuators_state,
            "system": {
                "scheduler_state": state_manager.get_state(f"scheduler_{device.id}")
            },
            "automation": {
                "rules_result": rules_result,
                "thresholds": thresholds
            }
        })

    # return results if len(results) > 1 else results[0]

    return results


def control_actuator(db: Session, actuator_type: str, on: bool, user_id: int, device_id: Optional[int] = None):
    device_id_str = str(device_id) if device_id is not None else None
    actuator_controller.control_actuator(db, actuator_type, on, device_id_str)

def control_actuator_by_id(db: Session, actuator_id: int, on: bool):
    return actuator_controller.control_actuator_by_id(db, actuator_id, on)
def control_pump(db: Session, on: bool, user_id: int, device_id: Optional[int] = None):
    control_actuator(db, "pump", on, user_id, device_id)

def control_light(db: Session, on: bool, user_id: int, device_id: Optional[int] = None):
    control_actuator(db, "light", on, user_id, device_id)

def control_fan(db: Session, on: bool, user_id: int, device_id: Optional[int] = None):
    control_actuator(db, "fan", on, user_id, device_id)

def control_water_pump(db: Session, on: bool, user_id: int, device_id: Optional[int] = None):
    control_actuator(db, "water_pump", on, user_id, device_id)

def refill_water_tank(db: Session, user_id: int, device_id: Optional[int] = None, duration_seconds: int = 300):
    logger.info(f"User {user_id} - Starting water tank refill for {duration_seconds} seconds on device {device_id or 'default'}")
    control_water_pump(db, True, user_id, device_id)

    return {
        "message": f"Water tank refill started for {duration_seconds} seconds",
        "duration": duration_seconds,
        "status": "running",
        "device_id": device_id
    }


def emergency_stop(db: Session, user_id: int):
    logger.warning(f"EMERGENCY STOP activated for user {user_id} - turning off all actuators")

    devices = hydro_device_service.get_devices_by_user(db, user_id)
    for device in devices:
        for actuator_type in ["pump", "light", "fan", "water_pump"]:
            try:
                actuator_controller.control_actuator(db, actuator_type, on=False, device_id=str(device.id))
            except Exception as e:
                logger.warning(f"Failed to stop {actuator_type} for device {device.id}: {e}")

    return {
        "message": f"Emergency stop completed for user {user_id}",
        "devices_stopped": [d.id for d in devices]
    }


def scheduler_control(action: str, user_id: Optional[int] = None, device_id: Optional[int] = None):
    if action == "start":
        start_sensor_job()
        if device_id:
            state_manager.set_state(f"scheduler_{device_id}", True)
        else:
            state_manager.set_state("scheduler", True)

    elif action == "stop":
        stop_sensor_job()
        if device_id:
            state_manager.set_state(f"scheduler_{device_id}", False)
        else:
            state_manager.set_state("scheduler", False)

    elif action == "restart":
        restart_sensor_job()
        if device_id:
            state_manager.set_state(f"scheduler_{device_id}", True)
        else:
            state_manager.set_state("scheduler", True)

    logger.info(f"Scheduler {action} command executed")

