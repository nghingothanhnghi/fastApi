# app/hydro_system/routes/actuator_router.py
# Description: This file contains the routes for hydro actuators.

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.hydro_system.schemas.actuator import (
    HydroActuatorCreate,
    HydroActuatorUpdate,
    HydroActuatorOut,
)
from app.hydro_system.services import actuator_service

router = APIRouter(prefix="/actuators", tags=["Hydro - Actuators"])

@router.post("/", response_model=HydroActuatorOut)
def create_actuator(actuator_in: HydroActuatorCreate, db: Session = Depends(get_db)):
    return actuator_service.create_actuator(db, actuator_in)

@router.get("/{actuator_id}", response_model=HydroActuatorOut)
def read_actuator(actuator_id: int, db: Session = Depends(get_db)):
    actuator = actuator_service.get_actuator(db, actuator_id)
    if not actuator:
        raise HTTPException(status_code=404, detail="Actuator not found")
    return actuator

@router.get("/device/{device_id}", response_model=list[HydroActuatorOut])
def list_actuators_by_device(device_id: int, db: Session = Depends(get_db)):
    return actuator_service.get_actuators_by_device(db, device_id)

@router.put("/{actuator_id}", response_model=HydroActuatorOut)
def update_actuator(actuator_id: int, actuator_in: HydroActuatorUpdate, db: Session = Depends(get_db)):
    actuator = actuator_service.update_actuator(db, actuator_id, actuator_in)
    if not actuator:
        raise HTTPException(status_code=404, detail="Actuator not found")
    return actuator

@router.delete("/{actuator_id}")
def delete_actuator(actuator_id: int, db: Session = Depends(get_db)):
    actuator = actuator_service.delete_actuator(db, actuator_id)
    if not actuator:
        raise HTTPException(status_code=404, detail="Actuator not found")
    return {"detail": "Actuator deleted successfully"}
