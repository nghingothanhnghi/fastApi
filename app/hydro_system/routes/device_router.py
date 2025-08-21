# app/hydro_system/routes/device_router.py

from fastapi import APIRouter, Query, Depends, Body, Path
from sqlalchemy.orm import Session
from typing import Optional, List

from app.database import get_db
from app.user.utils.token import get_current_user
from app.user.utils.role_requirements import require_roles
from app.user.enums.role_enum import RoleEnum
from app.user.models.user import User
from app.hydro_system.schemas.device import (
    HydroDeviceCreate, HydroDeviceUpdate, HydroDeviceOut
)
from app.hydro_system.controllers import device_controller



device_router = APIRouter()

# ========================
# 📦 DEVICE (ESP32) CRUD ENDPOINTS
# ========================
@device_router.get("", response_model=List[HydroDeviceOut])
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
    SuperAdmin can view all devices.
    """
    if RoleEnum.SUPER_ADMIN in current_user.roles:
        return device_controller.get_all_devices(db, skip=skip, limit=limit)

    if user_id is not None:
        return device_controller.get_devices_by_user(db, user_id)

    if client_id is not None:
        return device_controller.get_devices_by_client(db, client_id, skip=skip, limit=limit)

    return device_controller.get_devices_by_client(db, current_user.client_id, skip=skip, limit=limit)


@device_router.get("/{device_id}", response_model=HydroDeviceOut)
def get_device(
    device_id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
):
    """Get a device by ID"""
    return device_controller.get_device(db, device_id)


@device_router.post("", response_model=HydroDeviceOut, status_code=201)
def create_device(
    device_in: HydroDeviceCreate = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new device and auto-assign current user's user_id and client_id"""
    # Inject authenticated user details
    device_in.user_id = current_user.id
    device_in.client_id = current_user.client_id
    """Create a new device"""
    return device_controller.create_device(db, device_in)


@device_router.put("/{device_id}", response_model=HydroDeviceOut)
def update_device(
    device_id: int = Path(..., gt=0),
    updates: HydroDeviceUpdate = Body(...),
    db: Session = Depends(get_db),
):
    """Update an existing device"""
    return device_controller.update_device(db, device_id, updates)


@device_router.delete("/{device_id}")
def delete_device(
    device_id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
):
    """Delete a device by ID"""
    return device_controller.delete_device(db, device_id)
