# app/hydro_system/config.py
# Configuration settings for the hydroponic system

DEFAULT_THRESHOLDS = {
    "moisture_min": 30,        # percentage - minimum soil moisture
    "light_min": 300,          # lux - minimum light intensity
    "temperature_max": 28,     # degrees Celsius - maximum temperature
    "water_level_min": 20,     # percentage - minimum water level in tank
    "water_level_critical": 10 # percentage - critical water level (emergency alert)
}

DEVICE_IDS = {
    "pump": "device_pump_001",
    "light": "device_light_001",
    "fan": "device_fan_001",
    "water_pump": "device_water_pump_001",  # For refilling water tank
    "valve": "device_valve_001"             # For water flow control
}

# Water level sensor configuration
WATER_LEVEL_CONFIG = {
    "sensor_type": "ultrasonic",  # ultrasonic, float, pressure
    "tank_height_cm": 50,         # Total tank height in centimeters
    "max_volume_liters": 100,     # Maximum tank capacity in liters
    "calibration_offset": 2       # Sensor calibration offset in cm
}
