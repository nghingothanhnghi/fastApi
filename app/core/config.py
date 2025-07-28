# app/core/config.py
# Configuration settings for the application.
from dotenv import load_dotenv
import os

load_dotenv()

ADB_HOST = os.getenv("ADB_HOST", "127.0.0.1")
ADB_PORT = int(os.getenv("ADB_PORT", 5037))

USE_MOCK_DEVICES = os.getenv("USE_MOCK_DEVICES", "true").lower() in ("true", "1", "yes")

# Use mock AI for testing purposes transformation data, mapping.
USE_MOCK_AI = os.getenv("USE_MOCK_AI", "true").lower() in ("true", "1", "yes")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads/profile_images")
STATIC_URL_BASE = os.getenv("STATIC_URL_BASE", "/static/profile_images")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("Missing OPENAI_API_KEY in environment variables")
