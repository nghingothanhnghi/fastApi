# app/hydro_system/config.py

DEFAULT_THRESHOLDS = {
    "moisture_min": 30,        # percentage
    "light_min": 300,          # lux
    "temperature_max": 28      # degrees Celsius
}

DEVICE_IDS = {
    "pump": "device_pump_001",
    "light": "device_light_001",
    "fan": "device_fan_001"
}
