# app/hydro_system/config.py
# Configuration settings for the hydroponic system

# Configuration settings for the hydroponic system

# Default automation thresholds per device (can be overridden per device in DB)
DEFAULT_THRESHOLDS = {
    "moisture_min": 30,        # percentage - minimum soil moisture
    "light_min": 300,          # lux - minimum light intensity
    "temperature_max": 28,     # degrees Celsius - maximum temperature
    "water_level_min": 20,     # percentage - minimum water level in tank
    "water_level_critical": 10 # percentage - critical water level (emergency alert)
}

# Optional: Default actuator templates per device type
# Useful for initial device provisioning or testing
DEFAULT_ACTUATORS = [
    {
        "type": "pump",
        "name": "Pump A",
        "pin": "D1",
        "port": 1,
        "default_state": False
    },
    {
        "type": "light",
        "name": "Grow Light A",
        "pin": "D2",
        "port": 2,
        "default_state": False
    },
    {
        "type": "fan",
        "name": "Exhaust Fan A",
        "pin": "D3",
        "port": 3,
        "default_state": False
    },
    {
        "type": "water_pump",
        "name": "Refill Pump",
        "pin": "D4",
        "port": 4,
        "default_state": False
    },
    {
        "type": "valve",
        "name": "Water Valve",
        "pin": "D5",
        "port": 5,
        "default_state": False
    }
]

# Water level sensor configuration
WATER_LEVEL_CONFIG = {
    "sensor_type": "ultrasonic",  # ultrasonic, float, pressure
    "tank_height_cm": 50,         # Total tank height in centimeters
    "max_volume_liters": 100,     # Maximum tank capacity in liters
    "calibration_offset": 2       # Sensor calibration offset in cm
}

