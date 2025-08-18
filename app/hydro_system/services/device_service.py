# app/hydro_system/services/device_service.py
# Service class for managing hydro devices (ESP32)

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException
from typing import List, Optional
from app.hydro_system.models.device import HydroDevice
from app.hydro_system.models.actuator import HydroActuator
from app.hydro_system.schemas.device import HydroDeviceCreate, HydroDeviceUpdate
from app.core.config import USE_MOCK_HYDROSYSTEMMAINBOARD
from app.hydro_system.config import DEFAULT_ACTUATORS, DEVICE_IDS
from app.core.logging_config import get_logger

logger = get_logger(__name__)
class HydroDeviceService:
    def create_device(self, db: Session, device_in: HydroDeviceCreate) -> HydroDevice:
        logger.info(f"Attempting to create device: {device_in.device_id}")
        # Check for existing device_id (unique constraint)
        existing = db.query(HydroDevice).filter(HydroDevice.device_id == device_in.device_id).first()
        if existing:
            logger.warning(f"Device creation failed: Device ID '{device_in.device_id}' already exists.")
            raise HTTPException(status_code=400, detail="Device ID already exists.")

        try:
            device = HydroDevice(**device_in.dict())
            db.add(device)
            db.flush()  # Get device.id before commit
            logger.info(f"Created base device entry with ID: {device.id}")
            # Create default actuators for this device
            # for act in DEFAULT_ACTUATORS:
            #     actuator = HydroActuator(
            #         type=act["type"],
            #         name=act.get("name"),
            #         pin=act.get("pin"),
            #         port=act.get("port"),
            #         default_state=act.get("default_state", False),
            #         device_id=device.id,
            #     )
            #     db.add(actuator)
            #     logger.debug(f"Added actuator for device {device.device_id}: {actuator.type}")

             # --- MOCK MODE ---
            if USE_MOCK_HYDROSYSTEMMAINBOARD:
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
                    logger.debug(f"[MOCK] Added actuator for device {device.device_id}: {actuator.type}")
            else:
                logger.info(f"[REAL] Waiting for actuators from hardware for device {device.device_id}")

            db.commit()
            db.refresh(device)
            logger.info(f"Device '{device.device_id}' created successfully with {len(DEFAULT_ACTUATORS)} actuators.")
            return device
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Failed to create device: {e}")
            raise HTTPException(status_code=500, detail="Failed to create device.")

    def get_first_active_device(self, db: Session) -> Optional[HydroDevice]:
        device = db.query(HydroDevice).filter(HydroDevice.is_active == True).order_by(HydroDevice.created_at.asc()).first()
        if device:
            logger.debug(f"First active device found: {device.device_id}")
        else:
            logger.debug("No active device found in database.")
        return device

    def get_fallback_device_id(self, db: Session) -> str:
        """Returns a valid device_id from DB or uses a default from config."""
        device = self.get_first_active_device(db)
        if device:
            logger.info(f"Using active device from DB: {device.device_id}")
            return device.device_id  # use existing DB device_id
        elif DEVICE_IDS:
            logger.info(f"No device in DB. Using fallback DEVICE_ID: {DEVICE_IDS[0]}")
            return DEVICE_IDS[0]  # use default from config
        else:
            logger.error("No device available and no fallback DEVICE_IDS configured.")
            raise HTTPException(status_code=404, detail="No device available and no default configured.")

    def get_or_create_default_device(self, db: Session) -> HydroDevice:
        """Get the first active device from DB or create one from config."""
        device = self.get_first_active_device(db)
        if device:
            logger.info(f"Using existing active device: {device.device_id}")
            return device

        if not DEVICE_IDS:
            logger.error("No DEVICE_IDS configured for fallback.")
            raise HTTPException(status_code=404, detail="No fallback DEVICE_IDS configured.")

        fallback_id = DEVICE_IDS[0]
        logger.warning(f"No active device found. Creating fallback device with ID: {fallback_id}")

        # Use hardcoded defaults, or enhance to use a config object
        device_data = HydroDeviceCreate(
            device_id=fallback_id,
            name="Default Device",
            user_id=None,  # or some default user/client if needed
            client_id=None,
            is_active=True,
        )
        return self.create_device(db, device_data)


    def get_device(self, db: Session, device_id: int) -> Optional[HydroDevice]:
        logger.debug(f"Fetching device by internal ID: {device_id}")
        return db.query(HydroDevice).filter(HydroDevice.id == device_id).first()

    def get_device_by_external_id(self, db: Session, external_id: str) -> Optional[HydroDevice]:
        logger.debug(f"Fetching device by external ID: {external_id}")
        return db.query(HydroDevice).filter(HydroDevice.device_id == external_id).first()

    def get_devices_by_user(self, db: Session, user_id: int) -> List[HydroDevice]:
        logger.debug(f"Fetching devices for user ID: {user_id}")
        return db.query(HydroDevice).filter(HydroDevice.user_id == user_id).all()

    def get_device_for_user(self, db: Session, device_id: int, user_id: int) -> Optional[HydroDevice]:
        logger.debug(f"Fetching device ID {device_id} for user ID: {user_id}")
        return db.query(HydroDevice).filter(HydroDevice.id == device_id, HydroDevice.user_id == user_id).first()

    def get_devices_by_client(self, db: Session, client_id: str, skip: int = 0, limit: int = 100) -> List[HydroDevice]:
        logger.debug(f"Fetching devices for client ID: {client_id} (skip={skip}, limit={limit})")
        return db.query(HydroDevice).filter(HydroDevice.client_id == client_id).offset(skip).limit(limit).all()

    def get_all_devices(self, db: Session, skip: int = 0, limit: int = 100) -> List[HydroDevice]:
        logger.debug(f"Fetching all devices (skip={skip}, limit={limit})")
        return db.query(HydroDevice).offset(skip).limit(limit).all()

    def update_device(self, db: Session, device: HydroDevice, updates: HydroDeviceUpdate) -> HydroDevice:
        logger.info(f"Updating device ID: {device.id}")
        try:
            for field, value in updates.dict(exclude_unset=True).items():
                setattr(device, field, value)
                logger.debug(f"Updated '{field}' to '{value}'")
            db.commit()
            db.refresh(device)
            logger.info(f"Device ID {device.id} updated successfully.")
            return device
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Failed to update device ID {device.id}: {e}")
            raise e

    def delete_device(self, db: Session, device: HydroDevice) -> None:
        logger.warning(f"Deleting device ID: {device.id}")
        try:
            db.delete(device)
            db.commit()
            logger.info(f"Device ID {device.id} deleted successfully.")
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Failed to delete device ID {device.id}: {e}")
            raise e

# Export a single instance (singleton-style)
hydro_device_service = HydroDeviceService()
