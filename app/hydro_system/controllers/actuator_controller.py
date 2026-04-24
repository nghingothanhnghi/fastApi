# File: backend/app/hydro_system/controllers/actuator_controller.py
# Description: Hardware + actuator-based control logic for hydroponic system devices

from typing import Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload
from app.hydro_system.rules_engine import check_rules
from app.hydro_system.state_manager import set_state, get_state
from app.hydro_system.config import DEFAULT_ACTUATORS, ACTUATOR_TYPES, SUPPORTED_ACTUATOR_TYPES
from app.hydro_system.services.actuator_service import hydro_actuator_service
from app.hydro_system.services.actuator_log_service import log_actuator_action
from app.hydro_system.models.plant_batch import PlantBatch
from app.hydro_system.models.growth_stage import GrowthStage
from app.hydro_system.models.growth_recipe import GrowthRecipe

from app.core.logging_config import get_logger

logger = get_logger(__name__)


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

    state_str = "ON" if on else "OFF"

    if not actuators:
        fallback_id = DEFAULT_ACTUATORS.get(device_type, f"default_{device_type}_id")
        key = f"{device_type}_{fallback_id}"
        set_state(key, on)
        log_device_action("Default", device_type, on, fallback_id)
        log_actuator_action(db, actuator_id=None, action=state_str.lower(), state=state_str)
        return

    for actuator in actuators:
        key = f"{actuator.type}_{actuator.device_id}_{actuator.port}"
        set_state(key, on)
        log_device_action(actuator.name or actuator.type, actuator.type, on, actuator.device_id, actuator.id)
        log_actuator_action(db, actuator.id, action=state_str.lower(), state=state_str)


def control_actuator_by_id(db: Session, actuator_id: int, on: bool, source: str = "user"):
    """
    Control ONE actuator immediately (direct action).

    This function:
    - Executes hardware action NOW
    - Updates runtime state (state_manager)
    - Logs action

    ❗ IMPORTANT:
    - Does NOT define long-term behavior (manual/auto)
    - Used by: user actions, automation, scheduler
    """
    actuator = hydro_actuator_service.get_actuator(db, actuator_id)
    if not actuator:
        raise HTTPException(status_code=404, detail="Actuator not found")

    state_str = "ON" if on else "OFF"
    key = f"{actuator.type}_{actuator.device_id}_{actuator.port}"
    set_state(key, on)
    log_device_action(actuator.name or actuator.type, actuator.type, on, actuator.device_id, actuator.id)
    log_actuator_action(db, actuator.id, action=state_str.lower(), state=state_str, source=source)

    return {
        "message": f"{actuator.name or actuator.type} turned {'on' if on else 'off'}",
        "actuator_id": actuator_id,
        "new_state": on,
        "state_key": key
    }

def set_manual_mode(db: Session, actuator_id: int, state: Optional[bool]):
    """
    Set manual control mode for an actuator.
    Controller layer:
    - Calls service to update DB
    - Applies hardware state if needed
    
    state:
        True  -> force ON (manual_on)
        False -> force OFF (manual_off)
        None  -> AUTO (allow automation)

    Responsibilities:
    - Persist control mode in DB (manual_state)
    - Optionally apply state immediately
    - Define behavior for future automation cycles

    ❗ This is NOT just an action → it defines CONTROL AUTHORITY
    """
    actuator = hydro_actuator_service.set_manual_state(db, actuator_id, state)

    if not actuator:
        raise HTTPException(status_code=404, detail="Actuator not found")

    # 🔥 apply immediately
    if state is not None:
        control_actuator_by_id(db, actuator_id, state, source="manual")

    logger.info(
        f"[MANUAL MODE] Actuator {actuator_id} -> "
        f"{'ON' if state is True else 'OFF' if state is False else 'AUTO'}"
    )

    return {
        "actuator_id": actuator_id,
        "manual_state": state,
        "mode": (
            "manual_on" if state is True else
            "manual_off" if state is False else
            "auto"
        )
    }

# --- Automation handler for multiple actuators ---

def handle_automation(db: Session, sensor_data: dict, device_id: int = None):
    """
    Main automation engine.

    This runs periodically (scheduler) and decides actuator states.

    Priority logic:
    1️⃣ manual_state (highest priority)
    2️⃣ recipes (growth stage)
    3️⃣ thresholds (sensor rules)

    Responsibilities:
    - Evaluate rules
    - Apply actuator changes ONLY when needed
    - Avoid unnecessary toggling
    """
    alerts = []
    actions_taken = {}

    # 🌿 GET current GrowthRecipes for this device/zone
    recipes = []
    batch = db.query(PlantBatch).options(
        joinedload(PlantBatch.current_stage).joinedload(GrowthStage.recipes)
    ).filter(
        PlantBatch.zone_id == device_id,
        PlantBatch.status == "growing"
    ).first()

    if batch and batch.current_stage:
        recipes = batch.current_stage.recipes
        logger.debug(f"[Automation] Found {len(recipes)} recipes for Batch {batch.id}")

    for device_type in SUPPORTED_ACTUATOR_TYPES:
        actuators = hydro_actuator_service.get_all_actuators_by_type(db, device_type, device_id=device_id)

        if not actuators:
            logger.warning(f"No actuators found for type '{device_type}' on device '{device_id}'")
            continue

        for actuator in actuators:
            actuator_key = f"{device_type}_{actuator.device_id}_{actuator.port}"

            # 🛑 STEP 1: MANUAL OVERRIDE (HIGHEST PRIORITY)
            if actuator.manual_state is not None:
                desired_state = actuator.manual_state
                prev_state = get_state(actuator_key)

                if desired_state != prev_state:
                    control_actuator_by_id(db, actuator.id, desired_state, source="manual")
                    set_state(actuator_key, desired_state)

                    logger.info(f"[MANUAL OVERRIDE] {actuator_key} -> {desired_state}")

                # ❌ SKIP automation completely
                continue

            # 🛑 STEP 2: AUTOMATION (rules_engine)
            # Per-actuator or per-device thresholds
            thresholds_override = actuator.device.thresholds or {}

            # Pass recipes to check_rules
            rules_result = check_rules(
                sensor_data, 
                overrides=thresholds_override, 
                actuators=[actuator],
                recipes=recipes
            )
            
            # Find the action for this specific actuator
            action = next((a for a in rules_result.get("actions", []) if a["actuator_id"] == actuator.id), None)
            should_activate = action["on"] if action else None

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

