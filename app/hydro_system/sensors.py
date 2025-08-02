# backend/app/hydro_system/sensors.py
# This file is a hardware abstraction layer (or mock simulation) that reads the actual (or simulated) values from sensors.

import random
import logging
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.hydro_system.models.device import HydroDevice
from app.hydro_system.config import WATER_LEVEL_CONFIG

logger = logging.getLogger(__name__)

def read_temperature():
    return round(random.uniform(20.0, 30.0), 1)

def read_humidity():
    return round(random.uniform(40.0, 80.0), 1)

def read_light():
    return round(random.uniform(200.0, 800.0), 1)

def read_moisture():
    return round(random.uniform(20.0, 90.0), 1)

def read_water_level(config=WATER_LEVEL_CONFIG):
    # In the future, apply calibration here if needed
    raw_distance_cm = random.uniform(0, config["tank_height_cm"])  # Simulated
    water_percent = round(100 - ((raw_distance_cm + config["calibration_offset"]) / config["tank_height_cm"]) * 100, 1)
    water_percent = max(0, min(water_percent, 100))  # Clamp to 0-100%
    logger.info(f"Water level: {water_percent}% (raw: {raw_distance_cm} cm)")
    return water_percent

def read_sensors(device_id: int = None):
    logger.info(f"📡 Reading sensors for device {device_id}")

    session: Session = SessionLocal()
    try:
        # Optional: Load device-specific config if needed
        device = None
        if device_id:
            device = session.query(HydroDevice).filter(HydroDevice.id == device_id).first()
            # if not device:
            #     logger.warning(f"No device found with ID {device_id}")
            if device:
                device_name = device.name  # 👈 Get device_name
            else:
                logger.warning(f"No device found with ID {device_id}")

        # Simulated readings (replace with actual sensor reads in production)
        sensor_data = {
            "device_id": device_id,
            "device_name": device_name,  # 👈 Include in response
            "temperature": read_temperature(),
            "humidity": read_humidity(),
            "light": read_light(),
            "moisture": read_moisture(),
            "water_level": read_water_level(),  # You can pass device config here if needed
        }

        logger.info(f"📈 Sensor readings for device {device_id}: {sensor_data}")
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
            "water_level": None
        }
    finally:
        session.close()
