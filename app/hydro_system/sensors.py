# backend/app/hydro_system/sensors.py
# Description: This module provides functions to read sensor data for temperature and humidity.

def read_temperature():
    # simulate or read actual sensor value
    return 25.5

def read_humidity():
    # simulate or read actual sensor value
    return 60.2

def read_sensors():
    return {
        "temperature": read_temperature(),
        "humidity": read_humidity()
    }
