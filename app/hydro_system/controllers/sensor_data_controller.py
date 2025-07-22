from sqlalchemy.orm import Session
from app.hydro_system.models.sensor_data import SensorData
from app.hydro_system.schemas.sensor_data import SensorDataCreateSchema
from app.hydro_system.config import DEFAULT_THRESHOLDS
from datetime import datetime
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


def create_sensor_data(payload: SensorDataCreateSchema, db: Session):
    new_data = SensorData(
        temperature=payload.temperature,
        humidity=payload.humidity,
        light=payload.light,
        moisture=payload.moisture,
        created_at=datetime.utcnow(),
    )
    db.add(new_data)
    db.commit()
    db.refresh(new_data)
    return new_data
