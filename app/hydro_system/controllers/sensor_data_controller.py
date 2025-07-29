# app/hydro_system/controllers/sensor_data_controller.py
# This file defines business logic and database interaction for managing sensor data
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.hydro_system.models.sensor_data import SensorData
from app.hydro_system.schemas.sensor_data import SensorDataCreateSchema
from app.hydro_system.config import DEFAULT_THRESHOLDS, WATER_LEVEL_CONFIG
from app.hydro_system.rules_engine import get_water_level_status, check_rules
from app.hydro_system.services.device_service import hydro_device_service
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def get_latest_sensor_data(db: Session):
    return db.query(SensorData).order_by(SensorData.created_at.desc()).limit(10).all()

def get_thresholds():
    return DEFAULT_THRESHOLDS

def update_thresholds(thresholds: dict):
    DEFAULT_THRESHOLDS.update(thresholds)
    logger.info(f"Thresholds updated: {thresholds}")
    return DEFAULT_THRESHOLDS


# def create_sensor_data(payload: SensorDataCreateSchema, db: Session):
#     new_data = SensorData(
#         temperature=payload.temperature,
#         humidity=payload.humidity,
#         light=payload.light,
#         moisture=payload.moisture,
#         water_level=payload.water_level,
#         created_at=datetime.utcnow(),
#     )
#     db.add(new_data)
#     db.commit()
#     db.refresh(new_data)
#     logger.info(f"New sensor data created: ID={new_data.id}, water_level={new_data.water_level}%")
#     return new_data
def create_sensor_data(payload: SensorDataCreateSchema, db: Session):
    # Lookup HydroDevice by external_id
    device = hydro_device_service.get_device_by_external_id(db, payload.device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device with external_id '{payload.device_id}' not found")

    new_data = SensorData(
        temperature=payload.temperature,
        humidity=payload.humidity,
        light=payload.light,
        moisture=payload.moisture,
        water_level=payload.water_level,
        device_id=device.id,
        created_at=datetime.utcnow(),
    )
    db.add(new_data)
    db.commit()
    db.refresh(new_data)
    logger.info(f"New sensor data created: ID={new_data.id}, water_level={new_data.water_level}%, device_id={device.id}")
    return new_data


def get_water_level_history(db: Session, hours: int = 24):
    """Get water level history for the specified number of hours"""
    since = datetime.utcnow() - timedelta(hours=hours)
    return db.query(SensorData).filter(
        SensorData.created_at >= since,
        SensorData.water_level.isnot(None)
    ).order_by(SensorData.created_at.desc()).all()

def get_current_water_status(db: Session):
    """Get current water level status with analysis"""
    latest_data = db.query(SensorData).order_by(SensorData.created_at.desc()).first()
    
    if not latest_data or latest_data.water_level is None:
        return {
            "status": "unknown",
            "message": "No water level data available",
            "current_level": None
        }
    
    sensor_data = {
        "water_level": latest_data.water_level,
        "temperature": latest_data.temperature,
        "humidity": latest_data.humidity,
        "light": latest_data.light,
        "moisture": latest_data.moisture
    }
    
    water_status = get_water_level_status(sensor_data, DEFAULT_THRESHOLDS)
    rules_result = check_rules(sensor_data, DEFAULT_THRESHOLDS)
    
    return {
        **water_status,
        "last_updated": latest_data.created_at,
        "alerts": rules_result.get("alerts", []),
        "actions_required": rules_result.get("actions", {}),
        "tank_config": WATER_LEVEL_CONFIG
    }

def get_water_consumption_rate(db: Session, hours: int = 24):
    """Calculate water consumption rate over specified hours"""
    history = get_water_level_history(db, hours)
    
    if len(history) < 2:
        return {
            "consumption_rate": None,
            "message": "Insufficient data to calculate consumption rate"
        }
    
    # Sort by time (oldest first)
    history.sort(key=lambda x: x.created_at)
    
    start_level = history[0].water_level
    end_level = history[-1].water_level
    time_diff_hours = (history[-1].created_at - history[0].created_at).total_seconds() / 3600
    
    if time_diff_hours == 0:
        return {
            "consumption_rate": 0,
            "message": "No time difference in data points"
        }
    
    consumption_rate = (start_level - end_level) / time_diff_hours  # % per hour
    
    # Calculate estimated time until empty
    current_level = end_level
    hours_until_empty = None
    if consumption_rate > 0 and current_level > 0:
        hours_until_empty = current_level / consumption_rate
    
    return {
        "consumption_rate_percent_per_hour": round(consumption_rate, 2),
        "start_level": start_level,
        "current_level": current_level,
        "time_period_hours": round(time_diff_hours, 1),
        "hours_until_empty": round(hours_until_empty, 1) if hours_until_empty else None,
        "data_points": len(history)
    }
