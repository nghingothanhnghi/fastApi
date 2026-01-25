# app/core/config.py
# Configuration settings for the application.
from dotenv import load_dotenv
import os

load_dotenv()

ADB_HOST = os.getenv("ADB_HOST", "127.0.0.1")
ADB_PORT = int(os.getenv("ADB_PORT", 5037))

# Use mock devices for android testing purposes.
USE_MOCK_DEVICES = os.getenv("USE_MOCK_DEVICES", "true").lower() in ("true", "1", "yes")

# Use mock devices for mainboard (esp32) testing purposes.
USE_MOCK_HYDROSYSTEMMAINBOARD = os.getenv("USE_MOCK_HYDROSYSTEMMAINBOARD", "true").lower() in ("true", "1", "yes")

# Use mock AI for testing purposes transformation data, mapping.
USE_MOCK_AI = os.getenv("USE_MOCK_AI", "true").lower() in ("true", "1", "yes")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads/profile_images")
STATIC_URL_BASE = os.getenv("STATIC_URL_BASE", "/static/profile_images")

MEDIA_DIR = os.getenv("MEDIA_DIR", "uploads/products")
MEDIA_URL = os.getenv("MEDIA_URL", "/static/products")

QR_CODE_DIR = os.path.join(MEDIA_DIR, "qrcodes")
QR_CODE_URL = f"{MEDIA_URL}/qrcodes"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("Missing OPENAI_API_KEY in environment variables")
