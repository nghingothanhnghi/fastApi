# app/api/endpoints/sensor_data.py
# This file defines the API endpoints for managing sensor data in the hydroponics system.
from fastapi import APIRouter, Depends
from app.database import get_db
from sqlalchemy.orm import Session
from app.hydro_system.schemas.sensor_data import SensorDataSchema, SensorDataCreateSchema
from app.hydro_system.controllers import sensor_data_controller as controller
import logging

router = APIRouter(prefix="/sensor", tags=["Sensor Data"])

logger = logging.getLogger(__name__)

@router.get("/data", response_model=list[SensorDataSchema])
def get_latest_sensor_data(db: Session = Depends(get_db)):
    return controller.get_latest_sensor_data(db)

@router.get("/thresholds")
def get_thresholds():
    return controller.get_thresholds()

@router.post("/thresholds")
def update_thresholds(thresholds: dict):
    new = controller.update_thresholds(thresholds)
    return {"message": "Thresholds updated", "new": new}

@router.post("/data", response_model=SensorDataSchema)
def create_sensor_data(payload: SensorDataCreateSchema, db: Session = Depends(get_db)):
    return controller.create_sensor_data(payload, db)