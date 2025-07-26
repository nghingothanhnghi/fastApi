# app/hydro_system/routes/devices_hydro_system.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.utils.token import get_current_user
from app.hydro_system.services.device_service import device_services
from app.hydro_system.schemas.device import DeviceCreate, DeviceUpdate, DeviceOut
from app.user.models.user import User

router = APIRouter(prefix="/devices", tags=["Devices"])

@router.post("/", response_model=DeviceOut)
def create_device(device_in: DeviceCreate, db: Session = Depends(get_db)):
    return device_services.create_device(db, device_in)

@router.get("/me", response_model=List[DeviceOut])
def get_my_devices(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return device_services.get_devices_by_user(db, current_user.id)

@router.get("/{device_id}", response_model=DeviceOut)
def get_device(device_id: int, db: Session = Depends(get_db)):
    device = device_services.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

@router.put("/{device_id}", response_model=DeviceOut)
def update_device(device_id: int, updates: DeviceUpdate, db: Session = Depends(get_db)):
    device = device_services.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device_services.update_device(db, device, updates)

@router.delete("/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db)):
    device = device_services.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    device_services.delete_device(db, device)
    return {"detail": "Device deleted"}
