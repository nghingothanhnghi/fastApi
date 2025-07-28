# File: backend/app/api/endpoints/hydro_system.py
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
)

from typing import Optional, List

router = APIRouter(prefix="/hydro", tags=["Hydro System"])

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
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None)
):
    system_controller.control_pump(True, user_id=current_user.id, device_id=device_id)
    return {"status": "Irrigation pump turned on", "device": "pump"}

@router.post("/pump/off")
def pump_off(
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None)
):
    system_controller.control_pump(False, user_id=current_user.id, device_id=device_id)
    return {"status": "Irrigation pump turned off", "device": "pump"}

# --- Grow Light Control ---
@router.post("/light/on")
def light_on(
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None)
):
    system_controller.control_light(True, user_id=current_user.id, device_id=device_id)
    return {"status": "Grow lights turned on", "device": "light"}

@router.post("/light/off")
def light_off(
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None)
):
    system_controller.control_light(False, user_id=current_user.id, device_id=device_id)
    return {"status": "Grow lights turned off", "device": "light"}

# --- Ventilation Fan Control ---
@router.post("/fan/on")
def fan_on(
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None)
):
    system_controller.control_fan(True, user_id=current_user.id, device_id=device_id)
    return {"status": "Ventilation fan turned on", "device": "fan"}

@router.post("/fan/off")
def fan_off(
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None)
):
    system_controller.control_fan(False, user_id=current_user.id, device_id=device_id)
    return {"status": "Ventilation fan turned off", "device": "fan"}

# --- Water Tank Management ---
@router.post("/water-pump/on")
def water_pump_on(
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None)
):
    system_controller.control_water_pump(True, user_id=current_user.id, device_id=device_id)
    return {"status": "Water refill pump turned on", "device": "water_pump"}

@router.post("/water-pump/off")
def water_pump_off(
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None)
):
    system_controller.control_water_pump(False, user_id=current_user.id, device_id=device_id)
    return {"status": "Water refill pump turned off", "device": "water_pump"}

@router.post("/water-tank/refill")
def refill_water_tank(
    duration: int = Query(300, description="Refill duration in seconds", ge=30, le=1800),
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None),
):
    return system_controller.refill_water_tank(
        duration_seconds=duration, user_id=current_user.id, device_id=device_id
    )

# --- Emergency Controls ---
@router.post("/emergency-stop")
def emergency_stop(
    current_user: User = Depends(get_current_user)
):
    result = system_controller.emergency_stop(user_id=current_user.id)
    return result

# --- Scheduler Control ---
@router.post("/scheduler/start")
def start_schedule():
    """Start the sensor data collection scheduler"""
    system_controller.scheduler_control("start")
    return {"status": "Scheduler started"}

@router.post("/scheduler/stop")
def stop_schedule():
    """Stop the sensor data collection scheduler"""
    system_controller.scheduler_control("stop")
    return {"status": "Scheduler stopped"}

@router.post("/scheduler/restart")
def restart_schedule():
    """Restart the sensor data collection scheduler"""
    system_controller.scheduler_control("restart")
    return {"status": "Scheduler restarted"}


# ========================
# 📦 DEVICE CRUD ENDPOINTS
# ========================

@router.get("/devices", response_model=List[HydroDeviceOut])
def get_devices(
    user_id: Optional[int] = Query(None),
    client_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all devices or filter by user_id or client_id. 
    Defaults to current user's client_id if none provided.
    """
    # Prefer explicitly passed query parameters
    if user_id is not None:
        return device_controller.get_devices_by_user(db, user_id)
    if client_id is not None:
        return device_controller.get_devices_by_client(db, client_id)

    # Fallback: use current user's client_id
    return device_controller.get_devices_by_client(db, current_user.client_id, skip=skip, limit=limit)


@router.get("/devices/{device_id}", response_model=HydroDeviceOut)
def get_device(
    device_id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
):
    """Get a device by ID"""
    return device_controller.get_device(db, device_id)


@router.post("/devices", response_model=HydroDeviceOut, status_code=201)
def create_device(
    device_in: HydroDeviceCreate = Body(...),
    db: Session = Depends(get_db),
):
    """Create a new device"""
    return device_controller.create_device(db, device_in)


@router.put("/devices/{device_id}", response_model=HydroDeviceOut)
def update_device(
    device_id: int = Path(..., gt=0),
    updates: HydroDeviceUpdate = Body(...),
    db: Session = Depends(get_db),
):
    """Update an existing device"""
    return device_controller.update_device(db, device_id, updates)


@router.delete("/devices/{device_id}")
def delete_device(
    device_id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
):
    """Delete a device by ID"""
    return device_controller.delete_device(db, device_id)