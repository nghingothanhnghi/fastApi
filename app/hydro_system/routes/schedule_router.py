# app/hydro_system/routes/schedule_router.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.hydro_system.schemas.schedule import (
    HydroScheduleCreate,
    HydroScheduleUpdate,
    HydroScheduleOut,
)
from app.hydro_system.services.schedule_service import hydro_schedule_service

router = APIRouter(prefix="/schedules", tags=["Hydro - Schedules"])

@router.post("/", response_model=HydroScheduleOut)
def create_schedule(schedule_in: HydroScheduleCreate, db: Session = Depends(get_db)):
    return hydro_schedule_service.create_schedule(db, schedule_in)

@router.get("/{schedule_id}", response_model=HydroScheduleOut)
def read_schedule(schedule_id: int, db: Session = Depends(get_db)):
    schedule = hydro_schedule_service.get_schedule(db, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule

@router.get("/actuator/{actuator_id}", response_model=List[HydroScheduleOut])
def list_schedules_by_actuator(actuator_id: int, db: Session = Depends(get_db)):
    return hydro_schedule_service.get_schedules_by_actuator(db, actuator_id)

@router.patch("/{schedule_id}", response_model=HydroScheduleOut)
def patch_schedule(schedule_id: int, schedule_in: HydroScheduleUpdate, db: Session = Depends(get_db)):
    schedule = hydro_schedule_service.update_schedule(db, schedule_id, schedule_in)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule

@router.delete("/{schedule_id}")
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    success = hydro_schedule_service.delete_schedule(db, schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"detail": "Schedule deleted successfully"}
