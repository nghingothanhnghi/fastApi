# app/hydro_system/routes/flow_reading_router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict

from app.database import get_db
from app.hydro_system.schemas.flow_reading import FlowReadingCreate, FlowReadingOut
from app.hydro_system.services.flow_reading_service import flow_reading_service

router = APIRouter(prefix="/hydro/flow-readings", tags=["Hydro - Flow Sensor"])


@router.post("", response_model=FlowReadingOut)
def create_flow_reading(payload: FlowReadingCreate, db: Session = Depends(get_db)):
    try:
        return flow_reading_service.create_reading(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/actuator/{actuator_id}/latest", response_model=FlowReadingOut)
def get_latest_for_actuator(actuator_id: int, db: Session = Depends(get_db)):
    reading = flow_reading_service.get_latest_for_actuator(db, actuator_id)
    if not reading:
        raise HTTPException(status_code=404, detail="No flow readings for this actuator")
    return reading


@router.get("/actuator/{actuator_id}/history", response_model=List[FlowReadingOut])
def get_history_for_actuator(actuator_id: int, limit: int = 100, db: Session = Depends(get_db)):
    return flow_reading_service.get_history_for_actuator(db, actuator_id, limit)


@router.get("/location/{location}/latest")
def get_latest_for_location(location: str, db: Session = Depends(get_db)) -> Dict[int, float]:
    """Returns {actuator_id: flow_rate} for every flow-sensored actuator at a location."""
    return flow_reading_service.get_latest_for_location(db, location)