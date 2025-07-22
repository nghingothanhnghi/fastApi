# app/core/config.py
from dotenv import load_dotenv
import os

load_dotenv()

ADB_HOST = os.getenv("ADB_HOST", "127.0.0.1")
ADB_PORT = int(os.getenv("ADB_PORT", 5037))

USE_MOCK_DEVICES = os.getenv("USE_MOCK_DEVICES", "true").lower() in ("true", "1", "yes")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads/profile_images")
STATIC_URL_BASE = os.getenv("STATIC_URL_BASE", "/static/profile_images")
