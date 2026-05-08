# app/hydro_system/helpers/actuator_helper.py

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.hydro_system.models.actuator import HydroActuator
# from app.hydro_system.services.actuator_service import hydro_actuator_service
from app.hydro_system.services.device_service import hydro_device_service


def validate_actuator_access(db: Session, actuator_id: int, user_id: int):
    """
    Ensure actuator exists and belongs to the current user.
    Raises HTTPException if invalid.
    """

    actuator = db.query(HydroActuator).filter(
        HydroActuator.id == actuator_id
    ).first()
    
    if not actuator:
        raise HTTPException(status_code=404, detail="Actuator not found")

    # Validate ownership via device
    device = hydro_device_service.get_device_for_user(
        db, actuator.device_id, user_id
    )
    if not device:
        raise HTTPException(status_code=403, detail="Not authorized")

    return actuator

def validate_gpio_pin_available(
        db: Session,
        device_id: int,
        pin: str,
        exclude_actuator_id: Optional[int] = None,
    ):
    """
    Ensure GPIO pin is not already used
    by another actuator on the same device.

    Parameters:
    ----------
    db : Session
    SQLAlchemy DB session

    device_id : int
    Device that owns the actuator

    pin : str
        GPIO pin to validate

    exclude_actuator_id : Optional[int]
        Ignore this actuator ID during validation
        (used when editing existing actuator)
    """

    query = db.query(HydroActuator).filter(
        HydroActuator.device_id == device_id,
         HydroActuator.pin == str(pin),
    )

    # Exclude current actuator during update
    if exclude_actuator_id is not None:
        query = query.filter(
            HydroActuator.id != exclude_actuator_id
        )

    existing = query.first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=(
                f"GPIO pin {pin} is already used "
                f"by actuator '{existing.name or existing.type}'"
            )
        )

    return True