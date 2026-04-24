# app/hydro_system/controllers/hydro_system_controller.py
# Defines endpoints for controlling individual devices (pump, light, fan, water pump) and overall system status.
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
from app.hydro_system.models.plant_batch import PlantBatch
from app.hydro_system.models.growth_stage import GrowthStage
from sqlalchemy.orm import joinedload
from datetime import date
from app.core.logging_config import get_logger

logger = get_logger(__name__)

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

    # --- Loop through each device and gather its data ---
    for device in devices:
        # 1️⃣ Read current sensor values
        sensor_data = sensors.read_sensors(device_id=device.id)

        # 2️⃣ Determine thresholds for automation
        thresholds = device.thresholds if hasattr(device, "thresholds") and device.thresholds else DEFAULT_THRESHOLDS

        # 4️⃣ Get all actuators assigned to this device
        actuators = hydro_actuator_service.get_actuators_by_device(db, device.id)

        auto_actuators = [a for a in actuators if a.manual_state is None]
        
        # 3️⃣ Evaluate automation rules based on sensor values and thresholds
        rules_result = check_rules(
            sensor_data,
            thresholds,
            actuators=auto_actuators,
            recipes=[]
        ) if auto_actuators else {"actions": []}

        # 🔥 map rules → actuator
        rules_map = {a["actuator_id"]: a for a in rules_result["actions"]}

        actuators_state = []

        # --- Map each actuator's info and current state ---
        for actuator in actuators:
            # sensor_value = None
            # if actuator.sensor_key and actuator.sensor_key in sensor_data:
            #     sensor_value = sensor_data[actuator.sensor_key]
            sensor_value = sensor_data.get(actuator.sensor_key) if actuator.sensor_key else None
            
            # ✅ MANUAL MODE HANDLING
            if actuator.manual_state is not None:
                rule_info = {
                    "reason": "manual_override",
                    "interval_mode": None,
                    "oneshot": None,
                    "sensor_triggered": None,
                }
            else:
                rule_info = rules_map.get(actuator.id, {})

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
                # Get last known state from state_manager (True=ON, False=OFF)
                # "current_state": state_manager.get_state(f"{actuator.type}_{actuator.device_id}_{actuator.port}")

                # 🔥 REAL STATE
                "current_state": state_manager.get_state(
                    f"{actuator.type}_{actuator.device_id}_{actuator.port}"
                ),

                # 🔥 MANUAL CONTROL
                "manual_state": actuator.manual_state,
                "mode": (
                    "manual_on" if actuator.manual_state is True else
                    "manual_off" if actuator.manual_state is False else
                    "auto"
                ),

                # 🔍 DEBUG INFO
                "automation_reason": rule_info.get("reason"),
                "interval_mode": rule_info.get("interval_mode"),
                "oneshot": rule_info.get("oneshot"),
                "sensor_triggered": rule_info.get("sensor_triggered"),

            })      

        # 5️⃣ Get currently growing batch for this device
        batch_info = None
        batch = db.query(PlantBatch).options(
            joinedload(PlantBatch.plant),
            joinedload(PlantBatch.current_stage)
        ).filter(
            PlantBatch.zone_id == device.id,
            PlantBatch.status == "growing"
        ).first()

        if batch:
            days_growing = (date.today() - batch.start_date).days

              # ✅ NEW: load stages with recipes
            stages = db.query(GrowthStage).options(
                joinedload(GrowthStage.recipes)
            ).filter(
                GrowthStage.plant_id == batch.plant_id
            ).order_by(GrowthStage.day_start).all()

            # ✅ serialize stages
            stages_data = [
                {
                    "id": s.id,
                    "name": s.name,
                    "day_start": s.day_start,
                    "day_end": s.day_end,
                    "recipes": [
                        {
                            "id": r.id,
                            "actuator_type": r.actuator_type,
                            "action": r.action,
                            "start_time": r.start_time,
                            "end_time": r.end_time,
                            "interval_on_min": r.interval_on_min,
                            "interval_off_min": r.interval_off_min,
                        }
                        for r in s.recipes
                    ]
                }
                for s in stages
            ]

            batch_info = {
                "id": batch.id,
                "plant_name": batch.plant.name if batch.plant else "Unknown",
                "start_date": batch.start_date,
                "days_growing": days_growing,

                # ✅ stage info
                "current_stage": batch.current_stage.name if batch.current_stage else "None",
                "current_stage_id": batch.current_stage.id if batch.current_stage else None,

                # ✅ timeline
                "stages": stages_data,

                "status": batch.status
            }

        # --- Compile full device status ---
        results.append({
            "device_id": device.id,
            "device_name": device.name,
            "location": device.location,
            "sensors": sensor_data,
            "actuators": actuators_state,
            "growing_batch": batch_info,
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

def set_manual_mode(db: Session, actuator_id: int, state: Optional[bool]):
    """
    state:
      True  -> manual ON
      False -> manual OFF
      None  -> AUTO
    """
    return actuator_controller.set_manual_mode(db, actuator_id, state)

def control_pump(db: Session, on: bool, user_id: int, device_id: Optional[int] = None):
    control_actuator(db, "pump", on, user_id, device_id)

def control_light(db: Session, on: bool, user_id: int, device_id: Optional[int] = None):
    control_actuator(db, "light", on, user_id, device_id)

def control_fan(db: Session, on: bool, user_id: int, device_id: Optional[int] = None):
    control_actuator(db, "fan", on, user_id, device_id)

def control_water_pump(db: Session, on: bool, user_id: int, device_id: Optional[int] = None):
    control_actuator(db, "water_pump", on, user_id, device_id)

def control_nutrient_pump(db: Session, on: bool, user_id: int, device_id: Optional[int] = None):
    control_actuator(db, "nutrient_pump", on, user_id, device_id)

def control_valve(db: Session, on: bool, user_id: int, device_id: Optional[int] = None):
    control_actuator(db, "valve", on, user_id, device_id)

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
        from app.hydro_system.config import SUPPORTED_ACTUATOR_TYPES
        for actuator_type in SUPPORTED_ACTUATOR_TYPES:
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

