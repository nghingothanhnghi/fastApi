# File: backend/app/api/endpoints/hydro_system.py
# Description: This module defines the API endpoints for controlling the hydroponic system.
from fastapi import APIRouter, Query
from app.hydro_system.controllers import hydro_system_controller as controller
from typing import Optional

router = APIRouter(prefix="/hydro", tags=["Hydro System"])

@router.get("/status")
def get_status():
    """Get comprehensive system status including sensors, devices, and automation"""
    return controller.get_system_status()

# Irrigation Pump Control
@router.post("/pump/on")
def pump_on():
    """Turn on irrigation pump"""
    controller.control_pump(True)
    return {"status": "Irrigation pump turned on", "device": "pump"}

@router.post("/pump/off")
def pump_off():
    """Turn off irrigation pump"""
    controller.control_pump(False)
    return {"status": "Irrigation pump turned off", "device": "pump"}

# Grow Light Control
@router.post("/light/on")
def light_on():
    """Turn on grow lights"""
    controller.control_light(True)
    return {"status": "Grow lights turned on", "device": "light"}

@router.post("/light/off")
def light_off():
    """Turn off grow lights"""
    controller.control_light(False)
    return {"status": "Grow lights turned off", "device": "light"}

# Ventilation Fan Control
@router.post("/fan/on")
def fan_on():
    """Turn on ventilation fan"""
    controller.control_fan(True)
    return {"status": "Ventilation fan turned on", "device": "fan"}

@router.post("/fan/off")
def fan_off():
    """Turn off ventilation fan"""
    controller.control_fan(False)
    return {"status": "Ventilation fan turned off", "device": "fan"}

# Water Tank Management
@router.post("/water-pump/on")
def water_pump_on():
    """Turn on water tank refill pump"""
    controller.control_water_pump(True)
    return {"status": "Water refill pump turned on", "device": "water_pump"}

@router.post("/water-pump/off")
def water_pump_off():
    """Turn off water tank refill pump"""
    controller.control_water_pump(False)
    return {"status": "Water refill pump turned off", "device": "water_pump"}

@router.post("/water-tank/refill")
def refill_water_tank(
    duration: int = Query(300, description="Refill duration in seconds", ge=30, le=1800)
):
    """Start water tank refill for specified duration (30 seconds to 30 minutes)"""
    result = controller.refill_water_tank(duration)
    return result

# Emergency Controls
@router.post("/emergency-stop")
def emergency_stop():
    """Emergency stop - turn off all devices immediately"""
    result = controller.emergency_stop()
    return result

# Scheduler Control
@router.post("/scheduler/start")
def start_schedule():
    """Start the sensor data collection scheduler"""
    controller.scheduler_control("start")
    return {"status": "Scheduler started"}

@router.post("/scheduler/stop")
def stop_schedule():
    """Stop the sensor data collection scheduler"""
    controller.scheduler_control("stop")
    return {"status": "Scheduler stopped"}

@router.post("/scheduler/restart")
def restart_schedule():
    """Restart the sensor data collection scheduler"""
    controller.scheduler_control("restart")
    return {"status": "Scheduler restarted"}

