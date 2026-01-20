# backend/app/hydro_system/sensors.py
# This file is a hardware abstraction layer (mock simulation or real hardware).
# It automatically switches based on USE_MOCK_HYDROSYSTEMMAINBOARD from config.

import random
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.hydro_system.models.device import HydroDevice
from app.hydro_system.models.sensor_data import SensorData
from app.hydro_system.config import WATER_LEVEL_CONFIG
from app.core.config import USE_MOCK_HYDROSYSTEMMAINBOARD

from app.core.logging_config import get_logger

logger = get_logger(__name__)

# ------------------------------
# Mock implementations
# ------------------------------
def _mock_temperature():
    return round(random.uniform(20.0, 30.0), 1)

def _mock_humidity():
    return round(random.uniform(40.0, 80.0), 1)

def _mock_light():
    return round(random.uniform(200.0, 800.0), 1)

def _mock_moisture():
    return round(random.uniform(20.0, 90.0), 1)

def _mock_ec():
    return round(random.uniform(1.0, 2.5), 2)

def _mock_ppm():
    return round(random.uniform(500, 1500), 0)

def _mock_water_level(config=WATER_LEVEL_CONFIG):
    raw_distance_cm = random.uniform(0, config["tank_height_cm"])  # Simulated
    water_percent = round(100 - ((raw_distance_cm + config["calibration_offset"]) / config["tank_height_cm"]) * 100, 1)
    water_percent = max(0, min(water_percent, 100))  # Clamp to 0-100%
    logger.info(f"💧 Simulated water level: {water_percent}% (raw: {raw_distance_cm} cm)")
    return water_percent

# ------------------------------
# Real implementations (ESP32 / MicroPython hooks)
# ------------------------------
def _real_latest_sensor(field: str, device_id: int = None) -> float:
    session: Session = SessionLocal()
    try:
        query = session.query(SensorData)
        if device_id:
            query = query.filter(SensorData.device_id == device_id)
        latest = query.order_by(SensorData.created_at.desc()).first()
        if latest:
            value = getattr(latest, field, None)
            if value is not None:
                return float(value)
        logger.warning(f"⚠️ No sensor data found for {field} (device={device_id}), returning 0.0")
        return 0.0
    except Exception as e:
        logger.error(f"❌ Error fetching {field} from DB: {e}")
        return 0.0
    finally:
        session.close()


def _real_temperature(device_id=None): return _real_latest_sensor("temperature", device_id)
def _real_humidity(device_id=None):    return _real_latest_sensor("humidity", device_id)
def _real_light(device_id=None):       return _real_latest_sensor("light", device_id)
def _real_moisture(device_id=None):    return _real_latest_sensor("moisture", device_id)
def _real_ec(device_id=None):          return _real_latest_sensor("ec", device_id)
def _real_ppm(device_id=None):         return _real_latest_sensor("ppm", device_id)
def _real_water_level(device_id=None, config=WATER_LEVEL_CONFIG):
    return _real_latest_sensor("water_level", device_id)

# ------------------------------
# Public API (same names)
# ------------------------------

def read_temperature():
    return _mock_temperature() if USE_MOCK_HYDROSYSTEMMAINBOARD else _real_temperature()

def read_humidity():
    return _mock_humidity() if USE_MOCK_HYDROSYSTEMMAINBOARD else _real_humidity()

def read_light():
    return _mock_light() if USE_MOCK_HYDROSYSTEMMAINBOARD else _real_light()

def read_moisture():
    return _mock_moisture() if USE_MOCK_HYDROSYSTEMMAINBOARD else _real_moisture()

def read_ec():
    return _mock_ec() if USE_MOCK_HYDROSYSTEMMAINBOARD else _real_ec()

def read_ppm():
    return _mock_ppm() if USE_MOCK_HYDROSYSTEMMAINBOARD else _real_ppm()

def read_water_level(config=WATER_LEVEL_CONFIG):
    return _mock_water_level(config) if USE_MOCK_HYDROSYSTEMMAINBOARD else _real_water_level(config)

# ------------------------------
# Aggregated read + persistence
# ------------------------------
def read_sensors(device_id: int = None, persist: bool = True):
    """
    Read all sensors, optionally persist to DB.
    """
    logger.info(f"📡 Reading sensors for device {device_id} (mock={USE_MOCK_HYDROSYSTEMMAINBOARD})")

    session: Session = SessionLocal()
    try:
        device_name = None
        if device_id:
            device = session.query(HydroDevice).filter(HydroDevice.id == device_id).first()
            if device:
                device_name = device.name
            else:
                logger.warning(f"No device found with ID {device_id}")

        sensor_data = {
            "device_id": device_id,
            "device_name": device_name,
            "temperature": _real_temperature(device_id) if not USE_MOCK_HYDROSYSTEMMAINBOARD else _mock_temperature(),
            "humidity": _real_humidity(device_id) if not USE_MOCK_HYDROSYSTEMMAINBOARD else _mock_humidity(),
            "light": _real_light(device_id) if not USE_MOCK_HYDROSYSTEMMAINBOARD else _mock_light(),
            "moisture": _real_moisture(device_id) if not USE_MOCK_HYDROSYSTEMMAINBOARD else _mock_moisture(),
            "ec": _real_ec(device_id) if not USE_MOCK_HYDROSYSTEMMAINBOARD else _mock_ec(),
            "ppm": _real_ppm(device_id) if not USE_MOCK_HYDROSYSTEMMAINBOARD else _mock_ppm(),
            "water_level": _real_water_level(device_id) if not USE_MOCK_HYDROSYSTEMMAINBOARD else _mock_water_level(),
        }

        logger.info(f"📈 Sensor readings: {sensor_data}")

        # Only persist when mocking (ESP32 already persists in real mode)
        if USE_MOCK_HYDROSYSTEMMAINBOARD and persist and device_id:
            db_record = SensorData(
                device_id=device_id,
                temperature=sensor_data["temperature"],
                humidity=sensor_data["humidity"],
                light=sensor_data["light"],
                moisture=sensor_data["moisture"],
                ec=sensor_data["ec"],
                ppm=sensor_data["ppm"],
                water_level=sensor_data["water_level"],
            )
            session.add(db_record)
            session.commit()
            session.refresh(db_record)
            logger.info(f"✅ Sensor data saved with ID {db_record.id}")

        return sensor_data

    except Exception as e:
        logger.error(f"❌ Error reading sensors for device {device_id}: {e}")
        return {
            "device_id": device_id,
            "device_name": None,
            "temperature": None,
            "humidity": None,
            "light": None,
            "moisture": None,
            "ec": None,
            "ppm": None,
            "water_level": None
        }
    finally:
        session.close()
