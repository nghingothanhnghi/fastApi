# File: backend/app/hydro_system/controllers/actuator_controller.py
# Description: Hardware + actuator-based control logic for hydroponic system devices

import logging
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.hydro_system.rules_engine import check_rules
from app.hydro_system.state_manager import set_state, get_state
from app.hydro_system.config import DEFAULT_ACTUATORS, ACTUATOR_TYPES, SUPPORTED_ACTUATOR_TYPES
from app.hydro_system.services.actuator_service import hydro_actuator_service
from app.hydro_system.services.actuator_log_service import log_actuator_action


logger = logging.getLogger(__name__)


def log_device_action(name: str, device_type: str, state: bool, device_id: str = None, actuator_id: int = None):
    """Log actuator action with emoji and readable output."""
    type_info = ACTUATOR_TYPES.get(device_type, {})
    emoji = type_info.get("emoji_on" if state else "emoji_off", "✅")
    state_str = "ON" if state else "OFF"
    label = type_info.get("label", device_type.title())
    logger.info(f"Turning {state_str} {label}: {device_id} (Actuator ID: {actuator_id})")
    print(f"{emoji} {label} '{name}' ({device_id}) turned {state_str}")


def control_actuator(db: Session, device_type: str, on: bool, device_id: str = None):
    """Control all actuators of a given type on the device"""
    actuators = hydro_actuator_service.get_all_actuators_by_type(db, device_type, device_id=device_id)

    if not actuators:
        fallback_id = DEFAULT_ACTUATORS.get(device_type, f"default_{device_type}_id")
        key = f"{device_type}_{fallback_id}"
        set_state(key, on)
        log_device_action("Default", device_type, on, fallback_id)
        log_actuator_action(db, None, on)
        return

    for actuator in actuators:
        key = f"{actuator.type}_{actuator.device_id}_{actuator.port}"
        set_state(key, on)
        log_device_action(actuator.name or actuator.type, actuator.type, on, actuator.device_id, actuator.id)
        log_actuator_action(db, actuator.id, on)


def control_actuator_by_id(db: Session, actuator_id: int, on: bool):
    """Control a specific actuator directly by its ID"""
    actuator = hydro_actuator_service.get_actuator(db, actuator_id)
    if not actuator:
        raise HTTPException(status_code=404, detail="Actuator not found")

    key = f"{actuator.type}_{actuator.device_id}_{actuator.port}"
    set_state(key, on)
    log_device_action(actuator.name or actuator.type, actuator.type, on, actuator.device_id, actuator.id)
    log_actuator_action(db, actuator.id, on)

    return {
        "message": f"{actuator.name or actuator.type} turned {'on' if on else 'off'}",
        "actuator_id": actuator_id,
        "new_state": on,
        "state_key": key
    }


# --- Individual device control using combined logic ---

# def turn_pump_on(db: Session, device_id: str = None): control_actuator(db, "pump", True, device_id)
# def turn_pump_off(db: Session, device_id: str = None): control_actuator(db, "pump", False, device_id)

# def turn_light_on(db: Session, device_id: str = None): control_actuator(db, "light", True, device_id)
# def turn_light_off(db: Session, device_id: str = None): control_actuator(db, "light", False, device_id)

# def turn_fan_on(db: Session, device_id: str = None): control_actuator(db, "fan", True, device_id)
# def turn_fan_off(db: Session, device_id: str = None): control_actuator(db, "fan", False, device_id)

# def turn_water_pump_on(db: Session, device_id: str = None): control_actuator(db, "water_pump", True, device_id)
# def turn_water_pump_off(db: Session, device_id: str = None): control_actuator(db, "water_pump", False, device_id)

# def open_valve(db: Session, device_id: str = None): control_actuator(db, "valve", True, device_id)
# def close_valve(db: Session, device_id: str = None): control_actuator(db, "valve", False, device_id)

# --- Automation handler for multiple actuators ---

def handle_automation(db: Session, sensor_data: dict, device_id: str = None):
    """
    Automate actuator control based on sensor readings.
    Each actuator on the device is evaluated with possible threshold overrides.
    """
    alerts = []
    actions_taken = {}

    for device_type in SUPPORTED_ACTUATOR_TYPES:
        actuators = hydro_actuator_service.get_all_actuators_by_type(db, device_type, device_id=device_id)

        if not actuators:
            logger.warning(f"No actuators found for type '{device_type}' on device '{device_id}'")
            continue

        for actuator in actuators:
            # Per-actuator or per-device thresholds
            thresholds_override = actuator.device.thresholds or {}

            rules_result = check_rules(sensor_data, overrides=thresholds_override)
            should_activate = rules_result.get("actions", {}).get(device_type)

            actuator_key = f"{device_type}_{actuator.device_id}_{actuator.port}"
            prev_state = get_state(actuator_key)

            for alert in rules_result.get("alerts", []):
                level = alert.get("type", "info")
                message = alert.get("message", "")
                getattr(logger, level)(f"{level.upper()} ALERT: {message}")
                alerts.append(alert)

            if should_activate is not None and should_activate != prev_state:
                control_actuator_by_id(db, actuator.id, should_activate)
                set_state(actuator_key, should_activate)
                logger.info(f"[Automation] {device_type} ({actuator.device_id}) -> {should_activate}")
                actions_taken[actuator_key] = {
                    "activated": should_activate,
                    "overrides": thresholds_override
                }
            else:
                logger.debug(f"No change for {actuator_key}, remains {prev_state}")

    return {
        "actions_taken": actions_taken,
        "alerts": alerts,
        "sensor_data": sensor_data
    }

