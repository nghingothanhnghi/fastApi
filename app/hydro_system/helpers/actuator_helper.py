# app/hydro_system/helpers/actuator_helper.py

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.hydro_system.services.actuator_service import hydro_actuator_service
from app.hydro_system.services.device_service import hydro_device_service


def validate_actuator_access(db: Session, actuator_id: int, user_id: int):
    """
    Ensure actuator exists and belongs to the current user.
    Raises HTTPException if invalid.
    """

    actuator = hydro_actuator_service.get_actuator(db, actuator_id)
    if not actuator:
        raise HTTPException(status_code=404, detail="Actuator not found")

    # Validate ownership via device
    device = hydro_device_service.get_device_for_user(
        db, actuator.device_id, user_id
    )
    if not device:
        raise HTTPException(status_code=403, detail="Not authorized")

    return actuator