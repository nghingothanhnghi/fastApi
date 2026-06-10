# app/hydro_system/services/threshold_service.py

from sqlalchemy.orm import Session

from app.hydro_system.config import DEFAULT_THRESHOLDS
from app.hydro_system.models.device import HydroDevice


class ThresholdService:

    def get_for_device(
        self,
        device: HydroDevice
    ) -> dict:

        thresholds = dict(DEFAULT_THRESHOLDS)

        if device.thresholds:
            thresholds.update(device.thresholds)

        return thresholds

    def update_device_thresholds(
        self,
        db: Session,
        device_id: int,
        updates: dict
    ) -> HydroDevice:

        device = (
            db.query(HydroDevice)
            .filter(HydroDevice.id == device_id)
            .first()
        )

        if not device:
            raise ValueError(
                f"Device {device_id} not found"
            )

        current = dict(device.thresholds or {})

        current.update(updates)

        device.thresholds = current

        db.commit()
        db.refresh(device)

        return device


threshold_service = ThresholdService()