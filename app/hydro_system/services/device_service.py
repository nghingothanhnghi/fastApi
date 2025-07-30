# app/hydro_system/services/device_service.py
# Service class for managing hydro devices (ESP32)

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException
from typing import List, Optional
from app.hydro_system.models.device import HydroDevice
from app.hydro_system.models.actuator import HydroActuator
from app.hydro_system.schemas.device import HydroDeviceCreate, HydroDeviceUpdate
from app.hydro_system.config import DEFAULT_ACTUATORS

class HydroDeviceService:
    def create_device(self, db: Session, device_in: HydroDeviceCreate) -> HydroDevice:
        # Check for existing device_id (unique constraint)
        existing = db.query(HydroDevice).filter(HydroDevice.device_id == device_in.device_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Device ID already exists.")

        try:
            device = HydroDevice(**device_in.dict())
            db.add(device)
            db.flush()  # Get device.id before commit

            # Create default actuators for this device
            for act in DEFAULT_ACTUATORS:
                actuator = HydroActuator(
                    type=act["type"],
                    name=act.get("name"),
                    pin=act.get("pin"),
                    port=act.get("port"),
                    default_state=act.get("default_state", False),
                    device_id=device.id,
                )
                db.add(actuator)

            db.commit()
            db.refresh(device)
            return device
        except SQLAlchemyError as e:
            db.rollback()
            raise HTTPException(status_code=500, detail="Failed to create device.")

    def get_device(self, db: Session, device_id: int) -> Optional[HydroDevice]:
        return db.query(HydroDevice).filter(HydroDevice.id == device_id).first()

    def get_device_by_external_id(self, db: Session, external_id: str) -> Optional[HydroDevice]:
        return db.query(HydroDevice).filter(HydroDevice.device_id == external_id).first()

    def get_devices_by_user(self, db: Session, user_id: int) -> List[HydroDevice]:
        return db.query(HydroDevice).filter(HydroDevice.user_id == user_id).all()

    def get_device_for_user(self, db: Session, device_id: int, user_id: int) -> Optional[HydroDevice]:
        return (
            db.query(HydroDevice)
            .filter(HydroDevice.id == device_id, HydroDevice.user_id == user_id)
            .first()
        )

    def get_devices_by_client(self, db: Session, client_id: str) -> List[HydroDevice]:
        return db.query(HydroDevice).filter(HydroDevice.client_id == client_id).all()

    def get_all_devices(self, db: Session, skip: int = 0, limit: int = 100) -> List[HydroDevice]:
        return db.query(HydroDevice).offset(skip).limit(limit).all()

    def update_device(self, db: Session, device: HydroDevice, updates: HydroDeviceUpdate) -> HydroDevice:
        try:
            for field, value in updates.dict(exclude_unset=True).items():
                setattr(device, field, value)
            db.commit()
            db.refresh(device)
            return device
        except SQLAlchemyError as e:
            db.rollback()
            raise e

    def delete_device(self, db: Session, device: HydroDevice) -> None:
        try:
            db.delete(device)
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            raise e

# Export a single instance (singleton-style)
hydro_device_service = HydroDeviceService()
