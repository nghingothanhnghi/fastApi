# app/hydro_system/routes/hydro_system_router.py
# Description: This module defines the API endpoints for controlling the hydroponic system.
from fastapi import APIRouter, Query, Depends, Body, Path
from app.database import get_db
from app.user.utils.token import get_current_user
from app.user.models.user import User
from sqlalchemy.orm import Session
# Import controllers with aliases for clarity
from app.hydro_system.controllers import (
    system_controller
)

from typing import Optional, List
from app.hydro_system.routes.actuator_logs_router import actuator_log_router
from app.hydro_system.routes.device_router import device_router
from app.hydro_system.helpers.actuator_helper import validate_actuator_access

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

# --- Emergency Controls ---
@router.post("/emergency-stop")
def emergency_stop(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = system_controller.emergency_stop(db=db, user_id=current_user.id)
    return result


@router.post("/actuator/{actuator_id}/on", summary="Turn actuator ON by ID")
def turn_actuator_on(
    actuator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    validate_actuator_access(db, actuator_id, current_user.id)

    return system_controller.control_actuator_by_id(
        db, actuator_id=actuator_id, on=True
    )

@router.post("/actuator/{actuator_id}/off", summary="Turn actuator OFF by ID")
def turn_actuator_off(
    actuator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    validate_actuator_access(db, actuator_id, current_user.id)

    return system_controller.control_actuator_by_id(
        db, actuator_id=actuator_id, on=False
    )



@router.post("/actuator/{actuator_id}/manual", summary="Set actuator manual mode")
def set_manual_mode(
    actuator_id: int,
    state: Optional[bool] = Body(None, embed=True),  # true / false / null
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    state:
      true  -> force ON
      false -> force OFF
      null  -> AUTO mode (back to automation)
    """
    validate_actuator_access(db, actuator_id, current_user.id)

    result = system_controller.set_manual_mode(db, actuator_id, state)

    return {
            "success": True,
            "data": result,
            "message": "Manual mode updated successfully"
    }

# --- Scheduler Control ---
@router.post("/scheduler/start")
def start_schedule(
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None)
):
    """Start the sensor data collection scheduler"""
    system_controller.scheduler_control("start", user_id=current_user.id, device_id=device_id)
    return {"status": "Scheduler started", "device_id": device_id}


@router.post("/scheduler/stop")
def stop_schedule(
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None)
):
    """Stop the sensor data collection scheduler"""
    system_controller.scheduler_control("stop", user_id=current_user.id, device_id=device_id)
    return {"status": "Scheduler stopped", "device_id": device_id}


@router.post("/scheduler/restart")
def restart_schedule(
    current_user: User = Depends(get_current_user),
    device_id: Optional[int] = Query(None)
):
    """Restart the sensor data collection scheduler"""
    system_controller.scheduler_control("restart", user_id=current_user.id, device_id=device_id)
    return {"status": "Scheduler restarted", "device_id": device_id}


