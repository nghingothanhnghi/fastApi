# app/hydro_system/controllers/hydro_device_controller.py
# Define your controller functions device (esp32 controller)
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.hydro_system.services.device_service import hydro_device_service
from app.hydro_system.schemas.device import HydroDeviceCreate, HydroDeviceUpdate
from app.hydro_system.models.device import HydroDevice
from app.user.models.user import User
from app.user.enums.role_enum import RoleEnum
from app.core.logging_config import get_logger

logger = get_logger(__name__)

def _ensure_device_access(device: HydroDevice, current_user: User) -> None:
    """
    Ownership/tenant check for a single device, mirroring the pattern
    actuator_controller.validate_actuator_access already uses for
    actuator routes. SUPER_ADMIN bypasses (same rule get_devices()
    already applies for listing). Everyone else must own the device
    outright (user_id match) or belong to the same client/tenant
    (client_id match, when the device has one).
 
    Call this in every single-device write path (update, delete,
    activate/deactivate) - GET-by-id is intentionally left alone here
    since read access wasn't the reported gap, but the same check
    should probably be added there too if devices are meant to be
    private per-tenant rather than just not-writable-by-others.
    """
    if RoleEnum.SUPER_ADMIN in current_user.roles:
        return
    if device.user_id == current_user.id:
        return
    if device.client_id is not None and device.client_id == current_user.client_id:
        return
    raise HTTPException(status_code=403, detail="Not authorized for this device")

def create_device(db: Session, device_in: HydroDeviceCreate) -> HydroDevice:
    return hydro_device_service.create_device(db, device_in)

def get_or_create_default_device(db: Session) -> HydroDevice:
    return hydro_device_service.get_or_create_default_device(db)

def get_device(db: Session, device_id: int) -> HydroDevice:
    device = hydro_device_service.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

def get_devices_by_user(db: Session, user_id: int):
    devices = hydro_device_service.get_devices_by_user(db, user_id)
    return devices or []   # Always return a list

def get_devices_by_client(db: Session, client_id: str, skip: int = 0, limit: int = 100):
    devices = hydro_device_service.get_devices_by_client(db, client_id, skip=skip, limit=limit)
    return devices or []


def get_all_devices(db: Session, skip: int = 0, limit: int = 100):
    devices = hydro_device_service.get_all_devices(db, skip, limit)
    return devices or []

def update_device(db: Session, device_id: int, updates: HydroDeviceUpdate, current_user: User):
    device = hydro_device_service.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    _ensure_device_access(device, current_user)
    return hydro_device_service.update_device(db, device, updates)
 
def delete_device(db: Session, device_id: int, current_user: User):
    device = hydro_device_service.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    _ensure_device_access(device, current_user)
    hydro_device_service.delete_device(db, device)
    return {"detail": "Device deleted successfully"}
 
# Activation helpers
def activate_device(db: Session, device_id: int, current_user: User):
    device = hydro_device_service.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    _ensure_device_access(device, current_user)
    return hydro_device_service.set_device_active(db, device_id, True)
 
def deactivate_device(db: Session, device_id: int, current_user: User):
    device = hydro_device_service.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    _ensure_device_access(device, current_user)
    return hydro_device_service.set_device_active(db, device_id, False)


# High-level device control (delegates to service)
def control_devices_by_location(db: Session, location: str, on: bool) -> dict:
    return hydro_device_service.control_devices_by_location(db, location, on)
