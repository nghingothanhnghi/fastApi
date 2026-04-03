# app/hydro_system/services/schedule_service.py

from typing import List, Optional
from sqlalchemy.orm import Session
from app.hydro_system.models.actuator import HydroActuator
from app.hydro_system.models.schedule import HydroSchedule
from app.hydro_system.schemas.schedule import HydroScheduleCreate, HydroScheduleUpdate

class HydroScheduleService:
    def create_schedule(self, db: Session, schedule_in: HydroScheduleCreate) -> HydroSchedule:
        schedule = HydroSchedule(**schedule_in.dict())
        db.add(schedule)
        db.commit()
        db.refresh(schedule)
        return schedule

    def get_schedule(self, db: Session, schedule_id: int) -> Optional[HydroSchedule]:
        return db.query(HydroSchedule).filter(HydroSchedule.id == schedule_id).first()

    def get_schedules_by_actuator(self, db: Session, actuator_id: int) -> List[HydroSchedule]:
        return db.query(HydroSchedule).filter(HydroSchedule.actuator_id == actuator_id).all()

    def update_schedule(self, db: Session, schedule_id: int, updates: HydroScheduleUpdate) -> Optional[HydroSchedule]:
        schedule = self.get_schedule(db, schedule_id)
        if not schedule:
            return None
        
        update_data = updates.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(schedule, field, value)
        
        db.commit()
        db.refresh(schedule)
        return schedule

    def delete_schedule(self, db: Session, schedule_id: int) -> bool:
        schedule = self.get_schedule(db, schedule_id)
        if not schedule:
            return False
        
        db.delete(schedule)
        db.commit()
        return True

    # ✅ ADD THIS (for controller bulk insert)
    def bulk_create(self, db: Session, schedules: list[HydroSchedule], commit: bool = True):
        db.add_all(schedules)
        if commit:
            db.commit()

    def delete_by_device_and_source(self, db: Session, device_id: int, source: str):
        db.query(HydroSchedule).join(HydroActuator).filter(
            HydroActuator.device_id == device_id,
            HydroSchedule.source == source
        ).delete(synchronize_session=False)        

hydro_schedule_service = HydroScheduleService()
