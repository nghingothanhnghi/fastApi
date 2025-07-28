# backend/app/hydro_system/sensors.py
# This file is a hardware abstraction layer (or mock simulation) that reads the actual (or simulated) values from sensors.

import random
import logging

logger = logging.getLogger(__name__)

def read_temperature():
    """Read temperature sensor value in Celsius"""
    # Simulate or read actual sensor value
    # In production, this would interface with actual hardware
    return round(random.uniform(20.0, 30.0), 1)

def read_humidity():
    """Read humidity sensor value as percentage (0-100%)"""
    # Simulate or read actual sensor value
    return round(random.uniform(40.0, 80.0), 1)

def read_light():
    """Read light sensor value in lux"""
    # Simulate or read actual sensor value
    return round(random.uniform(200.0, 800.0), 1)

def read_moisture():
    """Read soil moisture sensor value as percentage (0-100%)"""
    # Simulate or read actual sensor value
    return round(random.uniform(20.0, 90.0), 1)

def read_water_level():
    """Read water level sensor value as percentage (0-100%)"""
    # Simulate or read actual sensor value
    # 0% = empty tank, 100% = full tank
    water_level = round(random.uniform(10.0, 95.0), 1)
    logger.info(f"Water level reading: {water_level}%")
    return water_level

def read_sensors(device_id: int = None):
    logger.info(f"Reading sensors for device {device_id}")
    """Read all sensor values and return as dictionary"""
    try:
        sensor_data = {
            "temperature": read_temperature(),
            "humidity": read_humidity(),
            "light": read_light(),
            "moisture": read_moisture(),
            "water_level": read_water_level()
        }
        logger.info(f"Sensor readings: {sensor_data}")
        return sensor_data
    except Exception as e:
        logger.error(f"Error reading sensors: {e}")
        return {
            "temperature": None,
            "humidity": None,
            "light": None,
            "moisture": None,
            "water_level": None
        }
