# app/hydro_system/controllers/sensor_data_controller.py
# This file defines business logic and database interaction for managing sensor data
from fastapi import HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.hydro_system.models.sensor_data import SensorData
from app.hydro_system.models.device import HydroDevice
from app.hydro_system.schemas.sensor_data import SensorDataCreateSchema
from app.hydro_system.config import DEFAULT_THRESHOLDS, WATER_LEVEL_CONFIG
from app.hydro_system.rules_engine import get_water_level_status, check_rules
from app.hydro_system.services.device_service import hydro_device_service

from app.core.logging_config import get_logger

logger = get_logger(__name__)

def get_latest_sensor_data(db: Session):
    return db.query(SensorData).order_by(SensorData.created_at.desc()).limit(10).all()


def get_thresholds():
    return DEFAULT_THRESHOLDS


def update_thresholds(thresholds: dict):
    DEFAULT_THRESHOLDS.update(thresholds)
    logger.info(f"Thresholds updated: {thresholds}")
    return DEFAULT_THRESHOLDS

def create_sensor_data(payload: SensorDataCreateSchema, db: Session):
    device = None

    # Handle external_id / code (string) or int FK
    if isinstance(payload.device_id, str):
        device = hydro_device_service.get_device_by_external_id(db, payload.device_id)
    elif isinstance(payload.device_id, int):
        device = db.query(HydroDevice).filter(HydroDevice.id == payload.device_id).first()

    if not device:
        raise HTTPException(
            status_code=404,
            detail=f"Device not found for identifier '{payload.device_id}'"
        )

    new_data = SensorData(
        temperature=payload.data.temperature,
        humidity=payload.data.humidity,
        light=payload.data.light,
        moisture=payload.data.moisture,
        water_level=payload.data.water_level,
        device_id=device.id,   # ✅ Always store DB FK
        created_at=datetime.utcnow(),
    )
    db.add(new_data)
    db.commit()
    db.refresh(new_data)

    logger.info(
        f"✅ New sensor data created: ID={new_data.id}, device_id={device.id}, "
        f"T={new_data.temperature}°C, H={new_data.humidity}%, WL={new_data.water_level}%"
    )
    return new_data


def get_water_level_history(db: Session, hours: int = 24):
    since = datetime.utcnow() - timedelta(hours=hours)
    return (
        db.query(SensorData)
        .filter(SensorData.created_at >= since, SensorData.water_level.isnot(None))
        .order_by(SensorData.created_at.desc())
        .all()
    )

def get_current_water_status(db: Session):
    devices = db.query(HydroDevice).filter(HydroDevice.is_active == True).all()
    if not devices:
        return {
            "status": "error",
            "message": "No active devices found",
            "devices": [],
        }

    results = []

    for device in devices:
        latest_data = (
            db.query(SensorData)
            .filter(SensorData.device_id == device.id)
            .order_by(SensorData.created_at.desc())
            .first()
        )

        if not latest_data or latest_data.water_level is None:
            results.append({
                "device_id": device.device_id,
                "device_name": device.name,
                "status": "unknown",
                "message": "No water level data",
                "current_level": None,
                "actions": [],
            })
            continue

        sensor_data = {
            "water_level": latest_data.water_level,
            "temperature": latest_data.temperature,
            "humidity": latest_data.humidity,
            "light": latest_data.light,
            "moisture": latest_data.moisture,
        }

        water_status = get_water_level_status(sensor_data, DEFAULT_THRESHOLDS)
        rules_result = check_rules(sensor_data, DEFAULT_THRESHOLDS, device=device)

        actions = []
        raw_actions = rules_result.get("actions", [])
        
        if isinstance(raw_actions, dict):  # fallback if old structure used
            raw_actions = [dict(type=k, **v) for k, v in raw_actions.items()]

        for decision in raw_actions:
            actions.append({
                "id": decision.get("id"),
                "type": decision.get("type"),
                "port": decision.get("port"),
                "action": decision.get("action"),
                "reason": decision.get("reason", "No reason provided"),
            })

        results.append({
            "device_id": device.device_id,
            "device_name": device.name,
            "current_level": latest_data.water_level,
            "status": water_status.get("status"),
            "message": water_status.get("message"),
            "actions": actions,
        })

    return {
        "status": "success",
        "devices": results,
    }



def get_water_consumption_rate(db: Session, hours: int = 24):
    history = get_water_level_history(db, hours)

    if len(history) < 2:
        return {
            "consumption_rate": None,
            "message": "Insufficient data to calculate consumption rate"
        }

    history.sort(key=lambda x: x.created_at)

    start_level = history[0].water_level
    end_level = history[-1].water_level
    time_diff_hours = (history[-1].created_at - history[0].created_at).total_seconds() / 3600

    if time_diff_hours == 0:
        return {
            "consumption_rate": 0,
            "message": "No time difference in data points"
        }

    consumption_rate = (start_level - end_level) / time_diff_hours

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
