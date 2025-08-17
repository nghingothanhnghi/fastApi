# app/hydro_system/services/actuator_service.py
# Actuator service functions, like type: valve, pump,  etc....
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.hydro_system.models.actuator import HydroActuator
from app.hydro_system.schemas.actuator import HydroActuatorCreate, HydroActuatorUpdate

class HydroActuatorService:

    def create_actuator(self, db: Session, actuator_in: HydroActuatorCreate) -> HydroActuator:
        try:
            actuator = HydroActuator(**actuator_in.dict())
            db.add(actuator)
            db.commit()
            db.refresh(actuator)
            return actuator
        except SQLAlchemyError as e:
            db.rollback()
            raise e

    def get_actuator(self, db: Session, actuator_id: int) -> Optional[HydroActuator]:
        return db.query(HydroActuator).filter(HydroActuator.id == actuator_id).first()

    def get_actuators_by_device(self, db: Session, device_id: int) -> List[HydroActuator]:
        return db.query(HydroActuator).filter(HydroActuator.device_id == device_id).all()

    def get_actuators_by_device_and_type(self, db: Session, device_id: int, actuator_type: str) -> List[HydroActuator]:
        return (
            db.query(HydroActuator)
            .filter(HydroActuator.device_id == device_id, HydroActuator.type == actuator_type)
            .all()
        )

    # def update_actuator(self, db: Session, actuator: HydroActuator, updates: HydroActuatorUpdate) -> HydroActuator:
    #     try:
    #         for field, value in updates.dict(exclude_unset=True).items():
    #             setattr(actuator, field, value)
    #         db.commit()
    #         db.refresh(actuator)
    #         return actuator
    #     except SQLAlchemyError as e:
    #         db.rollback()
    #         raise e

    # def delete_actuator(self, db: Session, actuator: HydroActuator) -> None:
    #     try:
    #         db.delete(actuator)
    #         db.commit()
    #     except SQLAlchemyError as e:
    #         db.rollback()
    #         raise e
    def update_actuator(self, db: Session, actuator_id: int, updates: HydroActuatorUpdate) -> Optional[HydroActuator]:
        actuator = self.get_actuator(db, actuator_id)
        if not actuator:
            return None
        try:
            for field, value in updates.dict(exclude_unset=True).items():
                setattr(actuator, field, value)
            db.commit()
            db.refresh(actuator)
            return actuator
        except SQLAlchemyError as e:
            db.rollback()
            raise e

    def delete_actuator(self, db: Session, actuator_id: int) -> bool:
        actuator = self.get_actuator(db, actuator_id)
        if not actuator:
            return False
        try:
            db.delete(actuator)
            db.commit()
            return True
        except SQLAlchemyError as e:
            db.rollback()
            raise e

    def get_all_actuators_by_type(self, db: Session, actuator_type: str, device_id: Optional[int] = None) -> List[HydroActuator]:
        query = db.query(HydroActuator).filter(HydroActuator.type == actuator_type)
        if device_id is not None:
            query = query.filter(HydroActuator.device_id == device_id)
        return query.all()

    def get_active_actuators_by_type(self, db: Session, actuator_type: str, device_id: Optional[int] = None) -> List[HydroActuator]:
        query = db.query(HydroActuator).filter(
            HydroActuator.type == actuator_type,
            HydroActuator.is_active == True
        )
        if device_id is not None:
            query = query.filter(HydroActuator.device_id == device_id)
        return query.all()

    def get_all_actuators(self, db: Session) -> List[HydroActuator]:
        return db.query(HydroActuator).all()

    def update_actuators_by_type(
        self, db: Session, device_id: int, actuator_type: str, value: bool
    ) -> List[HydroActuator]:
        """
        Toggle all actuators of a type on a device.
        """
        actuators = self.get_actuators_by_device_and_type(db, device_id, actuator_type)
        for actuator in actuators:
            actuator.default_state = value
        db.commit()
        return actuators    


# Export a single instance (singleton-style)
hydro_actuator_service = HydroActuatorService()



