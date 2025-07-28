# app/hydro_system/controllers/hydro_device_controller.py
# Define your controller functions device
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.hydro_system.services.device_service import hydro_device_service
from app.hydro_system.schemas.device import HydroDeviceCreate, HydroDeviceUpdate
from app.hydro_system.models.device import HydroDevice

def create_device(db: Session, device_in: HydroDeviceCreate) -> HydroDevice:
    return hydro_device_service.create_device(db, device_in)

def get_device(db: Session, device_id: int) -> HydroDevice:
    device = hydro_device_service.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

def get_devices_by_user(db: Session, user_id: int):
    return hydro_device_service.get_devices_by_user(db, user_id)

def get_devices_by_client(db: Session, client_id: str):
    return hydro_device_service.get_devices_by_client(db, client_id)

def get_all_devices(db: Session, skip: int = 0, limit: int = 100):
    return hydro_device_service.get_all_devices(db, skip, limit)

def update_device(db: Session, device_id: int, updates: HydroDeviceUpdate):
    device = hydro_device_service.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return hydro_device_service.update_device(db, device, updates)

def delete_device(db: Session, device_id: int):
    device = hydro_device_service.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    hydro_device_service.delete_device(db, device)
    return {"detail": "Device deleted successfully"}
