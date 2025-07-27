# File: backend/app/api/endpoints/hydro_system.py
# Description: This module defines the API endpoints for controlling the hydroponic system.
from fastapi import APIRouter, Query, Depends, Body, Path
from app.database import get_db
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

# @router.get("/status")
# def get_status():
#     """Get comprehensive system status including sensors, devices, and automation"""
#     return controller.get_system_status()

# # Irrigation Pump Control
# @router.post("/pump/on")
# def pump_on():
#     """Turn on irrigation pump"""
#     controller.control_pump(True)
#     return {"status": "Irrigation pump turned on", "device": "pump"}

# @router.post("/pump/off")
# def pump_off():
#     """Turn off irrigation pump"""
#     controller.control_pump(False)
#     return {"status": "Irrigation pump turned off", "device": "pump"}

# # Grow Light Control
# @router.post("/light/on")
# def light_on():
#     """Turn on grow lights"""
#     controller.control_light(True)
#     return {"status": "Grow lights turned on", "device": "light"}

# @router.post("/light/off")
# def light_off():
#     """Turn off grow lights"""
#     controller.control_light(False)
#     return {"status": "Grow lights turned off", "device": "light"}

# # Ventilation Fan Control
# @router.post("/fan/on")
# def fan_on():
#     """Turn on ventilation fan"""
#     controller.control_fan(True)
#     return {"status": "Ventilation fan turned on", "device": "fan"}

# @router.post("/fan/off")
# def fan_off():
#     """Turn off ventilation fan"""
#     controller.control_fan(False)
#     return {"status": "Ventilation fan turned off", "device": "fan"}

# # Water Tank Management
# @router.post("/water-pump/on")
# def water_pump_on():
#     """Turn on water tank refill pump"""
#     controller.control_water_pump(True)
#     return {"status": "Water refill pump turned on", "device": "water_pump"}

# @router.post("/water-pump/off")
# def water_pump_off():
#     """Turn off water tank refill pump"""
#     controller.control_water_pump(False)
#     return {"status": "Water refill pump turned off", "device": "water_pump"}

# @router.post("/water-tank/refill")
# def refill_water_tank(
#     duration: int = Query(300, description="Refill duration in seconds", ge=30, le=1800)
# ):
#     """Start water tank refill for specified duration (30 seconds to 30 minutes)"""
#     result = controller.refill_water_tank(duration)
#     return result

# # Emergency Controls
# @router.post("/emergency-stop")
# def emergency_stop():
#     """Emergency stop - turn off all devices immediately"""
#     result = controller.emergency_stop()
#     return result


# # Scheduler Control
# @router.post("/scheduler/start")
# def start_schedule():
#     """Start the sensor data collection scheduler"""
#     controller.scheduler_control("start")
#     return {"status": "Scheduler started"}

# @router.post("/scheduler/stop")
# def stop_schedule():
#     """Stop the sensor data collection scheduler"""
#     controller.scheduler_control("stop")
#     return {"status": "Scheduler stopped"}

# @router.post("/scheduler/restart")
# def restart_schedule():
#     """Restart the sensor data collection scheduler"""
#     controller.scheduler_control("restart")
#     return {"status": "Scheduler restarted"}

# --- System Status ---
@router.get("/status")
def get_status():
    """Get comprehensive system status including sensors, devices, and automation"""
    return system_controller.get_system_status()

# --- Irrigation Pump Control ---
@router.post("/pump/on")
def pump_on(user_id: Optional[int] = Query(None), device_id: Optional[int] = Query(None)):
    """Turn on irrigation pump"""
    system_controller.control_pump(True, user_id=user_id, device_id=device_id)
    return {"status": "Irrigation pump turned on", "device": "pump"}

@router.post("/pump/off")
def pump_off(user_id: Optional[int] = Query(None), device_id: Optional[int] = Query(None)):
    """Turn off irrigation pump"""
    system_controller.control_pump(False, user_id=user_id, device_id=device_id)
    return {"status": "Irrigation pump turned off", "device": "pump"}

# --- Grow Light Control ---
@router.post("/light/on")
def light_on(user_id: Optional[int] = Query(None), device_id: Optional[int] = Query(None)):
    """Turn on grow lights"""
    system_controller.control_light(True, user_id=user_id, device_id=device_id)
    return {"status": "Grow lights turned on", "device": "light"}

@router.post("/light/off")
def light_off(user_id: Optional[int] = Query(None), device_id: Optional[int] = Query(None)):
    """Turn off grow lights"""
    system_controller.control_light(False, user_id=user_id, device_id=device_id)
    return {"status": "Grow lights turned off", "device": "light"}

# --- Ventilation Fan Control ---
@router.post("/fan/on")
def fan_on(user_id: Optional[int] = Query(None), device_id: Optional[int] = Query(None)):
    """Turn on ventilation fan"""
    system_controller.control_fan(True, user_id=user_id, device_id=device_id)
    return {"status": "Ventilation fan turned on", "device": "fan"}

@router.post("/fan/off")
def fan_off(user_id: Optional[int] = Query(None), device_id: Optional[int] = Query(None)):
    """Turn off ventilation fan"""
    system_controller.control_fan(False, user_id=user_id, device_id=device_id)
    return {"status": "Ventilation fan turned off", "device": "fan"}

# --- Water Tank Management ---
@router.post("/water-pump/on")
def water_pump_on(user_id: Optional[int] = Query(None), device_id: Optional[int] = Query(None)):
    """Turn on water tank refill pump"""
    system_controller.control_water_pump(True, user_id=user_id, device_id=device_id)
    return {"status": "Water refill pump turned on", "device": "water_pump"}

@router.post("/water-pump/off")
def water_pump_off(user_id: Optional[int] = Query(None), device_id: Optional[int] = Query(None)):
    """Turn off water tank refill pump"""
    system_controller.control_water_pump(False, user_id=user_id, device_id=device_id)
    return {"status": "Water refill pump turned off", "device": "water_pump"}

@router.post("/water-tank/refill")
def refill_water_tank(
    duration: int = Query(300, description="Refill duration in seconds", ge=30, le=1800),
    user_id: Optional[int] = Query(None),
    device_id: Optional[int] = Query(None),
):
    """Start water tank refill for specified duration (30 seconds to 30 minutes)"""
    result = system_controller.refill_water_tank(duration_seconds=duration, user_id=user_id, device_id=device_id)
    return result

# --- Emergency Controls ---
@router.post("/emergency-stop")
def emergency_stop(user_id: Optional[int] = Query(None)):
    """Emergency stop - turn off all devices immediately"""
    result = system_controller.emergency_stop(user_id=user_id)
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
):
    """List all devices or filter by user_id or client_id"""
    if user_id is not None:
        return device_controller.get_devices_by_user(db, user_id)
    if client_id is not None:
        return device_controller.get_devices_by_client(db, client_id)
    return device_controller.get_all_devices(db, skip=skip, limit=limit)


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