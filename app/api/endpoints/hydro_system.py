# File: backend/app/api/endpoints/hydro_system.py
# Description: This module defines the API endpoints for controlling the hydroponic system.
from fastapi import APIRouter
from app.hydro_system.controllers import hydro_system_controller as controller

router = APIRouter(prefix="/hydro", tags=["Hydro System"])

@router.get("/status")
def get_status():
    return controller.get_system_status()

@router.post("/pump/on")
def pump_on():
    controller.control_pump(True)
    return {"status": "Pump turned on"}

@router.post("/pump/off")
def pump_off():
    controller.control_pump(False)
    return {"status": "Pump turned off"}

@router.post("/light/on")
def light_on():
    controller.control_light(True)
    return {"status": "Light turned on"}

@router.post("/light/off")
def light_off():
    controller.control_light(False)
    return {"status": "Light turned off"}

@router.post("/scheduler/start")
def start_schedule():
    controller.scheduler_control("start")
    return {"status": "Scheduler started"}

@router.post("/scheduler/stop")
def stop_schedule():
    controller.scheduler_control("stop")
    return {"status": "Scheduler stopped"}

@router.post("/scheduler/restart")
def restart_schedule():
    controller.scheduler_control("restart")
    return {"status": "Scheduler restarted"}

