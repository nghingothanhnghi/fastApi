# File: backend/app/hydro_system/controllers/actuator_controller.py
# Description: Hardware + actuator-based control logic for hydroponic system devices

import logging
from sqlalchemy.orm import Session
from app.hydro_system.rules_engine import check_rules
from app.hydro_system.state_manager import set_state, get_state
from app.hydro_system.config import DEFAULT_ACTUATORS
from app.hydro_system.services.actuator_service import get_actuator_by_device_and_type, get_all_actuators_by_type
from app.hydro_system.services.actuator_log_service import log_actuator_action


logger = logging.getLogger(__name__)


def log_device_action(device_type: str, state: bool, device_id: str = None):
    """Log and print control action"""
    emoji_on = {
        "pump": "✅",
        "light": "💡",
        "fan": "🌪️",
        "water_pump": "💧",
        "valve": "🔓",
    }
    emoji_off = {
        "pump": "❌",
        "light": "🌙",
        "fan": "🔇",
        "water_pump": "🚰",
        "valve": "🔒",
    }
    emoji = emoji_on[device_type] if state else emoji_off[device_type]
    state_str = "ON" if state else "OFF"

    logger.info(f"Turning {state_str} {device_type}: {device_id}")
    print(f"{emoji} {device_type.replace('_', ' ').title()} ({device_id}) turned {state_str}")


def control_actuator(db: Session, device_type: str, on: bool, device_id: str = None):
    """Control actuator with optional database logic"""
    if device_id:
        actuator = get_actuator_by_device_and_type(db, device_id, device_type)
        if actuator:
            set_state(f"{device_type}_{device_id}", on)
            log_device_action(device_type, on, device_id)
            log_actuator_action(db, actuator.id, on)  # <--- Added DB logging
            return

    # Fallback to default logic if no actuator or device_id
    fallback_id = DEFAULT_ACTUATORS.get(device_type, f"default_{device_type}_id")
    set_state(device_type, on)
    log_device_action(device_type, on, fallback_id)
    log_actuator_action(db, None, on)  # <--- Log as unknown actuator



# --- Individual device control using combined logic ---

def turn_pump_on(db: Session, device_id: str = None): control_actuator(db, "pump", True, device_id)
def turn_pump_off(db: Session, device_id: str = None): control_actuator(db, "pump", False, device_id)

def turn_light_on(db: Session, device_id: str = None): control_actuator(db, "light", True, device_id)
def turn_light_off(db: Session, device_id: str = None): control_actuator(db, "light", False, device_id)

def turn_fan_on(db: Session, device_id: str = None): control_actuator(db, "fan", True, device_id)
def turn_fan_off(db: Session, device_id: str = None): control_actuator(db, "fan", False, device_id)

def turn_water_pump_on(db: Session, device_id: str = None): control_actuator(db, "water_pump", True, device_id)
def turn_water_pump_off(db: Session, device_id: str = None): control_actuator(db, "water_pump", False, device_id)

def open_valve(db: Session, device_id: str = None): control_actuator(db, "valve", True, device_id)
def close_valve(db: Session, device_id: str = None): control_actuator(db, "valve", False, device_id)


# --- Automation handler (uses same interface) ---

def handle_automation(db: Session, sensor_data: dict, device_id: str = None):
    """
    Handle automated control based on sensor data for each actuator individually.
    Supports multiple actuators of the same type with optional per-actuator threshold overrides.
    """
    alerts = []
    actions_taken = {}

    for device_type in ["pump", "light", "fan", "water_pump", "valve"]:
        actuators = get_all_actuators_by_type(db, device_type, device_id=device_id)

        if not actuators:
            logger.warning(f"No actuators found for type '{device_type}' on device '{device_id}'")
            continue

        for actuator in actuators:
            # Use actuator-level override thresholds if defined
            thresholds_override = actuator.thresholds or {}

            # Re-run rules per actuator with their own overrides
            rules_result = check_rules(sensor_data, overrides=thresholds_override)
            should_activate = rules_result.get("actions", {}).get(device_type)

            actuator_key = f"{device_type}_{actuator.device_id}"
            prev_state = get_state(actuator_key)

            # Collect and log alerts (don't re-log duplicates)
            for alert in rules_result.get("alerts", []):
                level = alert.get("type", "info")
                message = alert.get("message", "")
                getattr(logger, level)(f"{level.upper()} ALERT: {message}")
                alerts.append(alert)

            # Decide whether to activate/deactivate actuator
            if should_activate is not None and should_activate != prev_state:
                control_actuator(db, device_type, should_activate, actuator.device_id)
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

