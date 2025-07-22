# app/api/endpoints/sensor_data.py
# This file defines the API endpoints for managing sensor data in the hydroponics system.
from fastapi import APIRouter, Depends, Query
from app.database import get_db
from sqlalchemy.orm import Session
from app.hydro_system.schemas.sensor_data import SensorDataSchema, SensorDataCreateSchema
from app.hydro_system.controllers import sensor_data_controller as controller
from typing import Optional
import logging

router = APIRouter(prefix="/sensor", tags=["Sensor Data"])

logger = logging.getLogger(__name__)

@router.get("/data", response_model=list[SensorDataSchema])
def get_latest_sensor_data(db: Session = Depends(get_db)):
    """Get the latest sensor data readings"""
    return controller.get_latest_sensor_data(db)

@router.get("/thresholds")
def get_thresholds():
    """Get current sensor thresholds for automation rules"""
    return controller.get_thresholds()

@router.post("/thresholds")
def update_thresholds(thresholds: dict):
    """Update sensor thresholds for automation rules"""
    new = controller.update_thresholds(thresholds)
    return {"message": "Thresholds updated", "new": new}

@router.post("/data", response_model=SensorDataSchema)
def create_sensor_data(payload: SensorDataCreateSchema, db: Session = Depends(get_db)):
    """Submit new sensor data reading"""
    return controller.create_sensor_data(payload, db)

@router.get("/water-level/status")
def get_water_level_status(db: Session = Depends(get_db)):
    """Get current water level status with analysis and recommendations"""
    return controller.get_current_water_status(db)

@router.get("/water-level/history", response_model=list[SensorDataSchema])
def get_water_level_history(
    hours: int = Query(24, description="Number of hours of history to retrieve", ge=1, le=168),
    db: Session = Depends(get_db)
):
    """Get water level history for the specified number of hours (max 7 days)"""
    return controller.get_water_level_history(db, hours)

@router.get("/water-level/consumption")
def get_water_consumption_analysis(
    hours: int = Query(24, description="Number of hours to analyze", ge=1, le=168),
    db: Session = Depends(get_db)
):
    """Analyze water consumption rate and predict when tank will be empty"""
    return controller.get_water_consumption_rate(db, hours)