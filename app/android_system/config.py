# app/android_system/config.py
# Configuration settings for Android device integration

import os
from app.core.config import ADB_HOST, ADB_PORT, USE_MOCK_DEVICES


# Screen Streaming Configuration
SCREEN_STREAM_CONFIG = {
    "fps": 15,                    # Target frames per second
    "quality": 70,                # JPEG quality (1-100)
    "format": "JPEG",             # Image format
    "timeout": 10,                # Connection timeout in seconds
}

# Touch Simulation Configuration
TOUCH_CONFIG = {
    "default_x": 500,             # Default tap X coordinate
    "default_y": 500,             # Default tap Y coordinate
    "swipe_duration": 300,        # Default swipe duration in ms
    "tap_delay": 100,             # Delay between taps in ms
}

# Device Discovery Configuration
DEVICE_CONFIG = {
    "discovery_timeout": 5,       # Device discovery timeout in seconds
    "connection_retry": 3,        # Number of connection retries
    "health_check_interval": 30,  # Health check interval in seconds
}

# Mock Device Serials (for testing)
MOCK_DEVICE_SERIALS = [
    "mock_device_001",
    "mock_device_002",
    "mock_device_003"
]

# Device Properties Template
DEFAULT_DEVICE_PROPERTIES = {
    "model": "Unknown",
    "device": "Unknown", 
    "android_version": "Unknown",
    "manufacturer": "Unknown",
    "brand": "Unknown",
    "sdk_version": "Unknown"
}