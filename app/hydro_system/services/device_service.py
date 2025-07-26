# app/hydro_system/services/device_service.py
from sqlalchemy.orm import Session
from app.hydro_system.models.device import Device
from app.hydro_system.schemas.device import DeviceCreate, DeviceUpdate

class DeviceService:
    def create_device(self, db: Session, device_in: DeviceCreate) -> Device:
        device = Device(**device_in.dict())
        db.add(device)
        db.commit()
        db.refresh(device)
        return device

    def get_device(self, db: Session, device_id: int) -> Device | None:
        return db.query(Device).filter(Device.id == device_id).first()

    def get_devices_by_user(self, db: Session, user_id: int):
        return db.query(Device).filter(Device.user_id == user_id).all()

    def update_device(self, db: Session, device: Device, updates: DeviceUpdate) -> Device:
        for field, value in updates.dict(exclude_unset=True).items():
            setattr(device, field, value)
        db.commit()
        db.refresh(device)
        return device

    def delete_device(self, db: Session, device: Device):
        db.delete(device)
        db.commit()

# Export a single instance (singleton-style)
device_services = DeviceService()
