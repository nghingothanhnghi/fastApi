# app/hydro_system/routes/hydro_system_router.py
# Description: This module defines the API endpoints for controlling the hydroponic system.
from fastapi import APIRouter, Query, Depends, Body, Path
from app.database import get_db
from app.utils.token import get_current_user
from app.user.models.user import User
from sqlalchemy.orm import Session
# from app.hydro_system.controllers import hydro_system_controller as controller
from app.hydro_system.schemas.device import (
    HydroDeviceCreate, HydroDeviceUpdate, HydroDeviceOut
)
# Import controllers with aliases for clarity
from app.hydro_system.controllers import (
    hydro_system_controller as system_controller,
    hydro_device_controller as device_controller,
    sensor_data_controller as sensor_controller,
    actuator_controller as actuator_controller
)

from typing import Optional, List
from app.hydro_system.routes.actuator_logs_router import actuator_log_router
from app.hydro_system.routes.device_router import device_router

router = APIRouter(prefix="/hydro", tags=["Hydro System"])
router.include_router(actuator_log_router, prefix="/actuator-logs")
router.include_router(device_router, prefix="/devices")

# --- System Status ---
@router.get("/status")
def get_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None)
):
    return system_controller.get_system_status(
        db=db, user_id=current_user.id, device_id=device_id
    )

# --- Irrigation Pump Control ---
@router.post("/pump/on")
def pump_on(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None)
):
    system_controller.control_pump(db, True, user_id=current_user.id, device_id=device_id)
    return {"status": "Irrigation pump turned on", "device": "pump"}

@router.post("/pump/off")
def pump_off(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None)
):
    system_controller.control_pump(db, False, user_id=current_user.id, device_id=device_id)
    return {"status": "Irrigation pump turned off", "device": "pump"}

# --- Grow Light Control ---
@router.post("/light/on")
def light_on(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None)
):
    system_controller.control_light(db, True, user_id=current_user.id, device_id=device_id)
    return {"status": "Grow lights turned on", "device": "light"}

@router.post("/light/off")
def light_off(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None)
):
    system_controller.control_light(db, False, user_id=current_user.id, device_id=device_id)
    return {"status": "Grow lights turned off", "device": "light"}

# --- Ventilation Fan Control ---
@router.post("/fan/on")
def fan_on(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None)
):
    system_controller.control_fan(db, True, user_id=current_user.id, device_id=device_id)
    return {"status": "Ventilation fan turned on", "device": "fan"}

@router.post("/fan/off")
def fan_off(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None)
):
    system_controller.control_fan(db, False, user_id=current_user.id, device_id=device_id)
    return {"status": "Ventilation fan turned off", "device": "fan"}

# --- Water Tank Management ---
@router.post("/water-pump/on")
def water_pump_on(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None)
):
    system_controller.control_water_pump(db, True, user_id=current_user.id, device_id=device_id)
    return {"status": "Water refill pump turned on", "device": "water_pump"}

@router.post("/water-pump/off")
def water_pump_off(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None)
):
    system_controller.control_water_pump(db, False, user_id=current_user.id, device_id=device_id)
    return {"status": "Water refill pump turned off", "device": "water_pump"}

@router.post("/water-tank/refill")
def refill_water_tank(
    duration: int = Query(300, description="Refill duration in seconds", ge=30, le=1800),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None),
):
    return system_controller.refill_water_tank(
        db=db, duration_seconds=duration, user_id=current_user.id, device_id=device_id
    )

# --- Emergency Controls ---
@router.post("/emergency-stop")
def emergency_stop(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = system_controller.emergency_stop(db=db, user_id=current_user.id)
    return result

# --- Scheduler Control ---
@router.post("/scheduler/start")
def start_schedule(
    current_user: User = Depends(get_current_user)
):
    """Start the sensor data collection scheduler"""
    system_controller.scheduler_control("start")
    return {"status": "Scheduler started"}

@router.post("/scheduler/stop")
def stop_schedule(
    current_user: User = Depends(get_current_user)
):
    """Stop the sensor data collection scheduler"""
    system_controller.scheduler_control("stop")
    return {"status": "Scheduler stopped"}

@router.post("/scheduler/restart")
def restart_schedule(
    current_user: User = Depends(get_current_user)
):
    """Restart the sensor data collection scheduler"""
    system_controller.scheduler_control("restart")
    return {"status": "Scheduler restarted"}
