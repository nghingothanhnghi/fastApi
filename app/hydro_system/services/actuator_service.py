# app/hydro_system/services/actuator_service.py
# Actuator service functions, like type: valve, pump,  etc....

from sqlalchemy.orm import Session
from app.hydro_system.models.actuator import HydroActuator
from app.hydro_system.schemas.actuator import HydroActuatorCreate, HydroActuatorUpdate

def create_actuator(db: Session, actuator_in: HydroActuatorCreate):
    actuator = HydroActuator(**actuator_in.dict())
    db.add(actuator)
    db.commit()
    db.refresh(actuator)
    return actuator

def get_actuator(db: Session, actuator_id: int):
    return db.query(HydroActuator).filter(HydroActuator.id == actuator_id).first()

def get_actuators_by_device(db: Session, device_id: int):
    return db.query(HydroActuator).filter(HydroActuator.device_id == device_id).all()

def get_actuator_by_device_and_type(db: Session, device_id: int, actuator_type: str):
    return (
        db.query(HydroActuator)
        .filter(
            HydroActuator.device_id == device_id,
            HydroActuator.type == actuator_type
        )
        .first()
    )

def update_actuator(db: Session, actuator_id: int, actuator_in: HydroActuatorUpdate):
    actuator = get_actuator(db, actuator_id)
    if not actuator:
        return None
    for field, value in actuator_in.dict(exclude_unset=True).items():
        setattr(actuator, field, value)
    db.commit()
    db.refresh(actuator)
    return actuator

def delete_actuator(db: Session, actuator_id: int):
    actuator = get_actuator(db, actuator_id)
    if actuator:
        db.delete(actuator)
        db.commit()
    return actuator

