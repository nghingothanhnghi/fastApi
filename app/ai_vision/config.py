# app/ai_vision/config.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() in ("true", "1", "yes")
AI_MODEL_NAME = os.getenv("AI_MODEL_NAME", "plant-detector")
AI_MODEL_VERSION = os.getenv("AI_MODEL_VERSION", "v1")
AI_CONFIDENCE_THRESHOLD = float(os.getenv("AI_CONFIDENCE_THRESHOLD", "0.60"))
AI_JOB_LEASE_SECONDS = int(os.getenv("AI_JOB_LEASE_SECONDS", "600"))

PLANT_HEALTH_WARNING_THRESHOLD = int(os.getenv("PLANT_HEALTH_WARNING_THRESHOLD", "70"))
PLANT_HEALTH_CRITICAL_THRESHOLD = int(os.getenv("PLANT_HEALTH_CRITICAL_THRESHOLD", "50"))

GROWTH_ANOMALY_THRESHOLD = float(os.getenv("GROWTH_ANOMALY_THRESHOLD", "0.30"))  # 30% deviation from baseline
# Fallback for when baseline_growth_rate_pct_per_day == 0.0: percent-based
# deviation is undefined there (division by zero), so instead we compare the
# absolute growth rate against this threshold. Without this, any change off
# a flat baseline was silently never flagged as anomalous.
GROWTH_ANOMALY_ABS_PCT_PER_DAY = float(os.getenv("GROWTH_ANOMALY_ABS_PCT_PER_DAY", "15.0"))
SENSOR_WINDOW_MINUTES = int(os.getenv("AI_SENSOR_WINDOW_MINUTES", "15"))

IMAGE_MAX_SIZE_MB = int(os.getenv("IMAGE_MAX_SIZE_MB", "10"))
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

# Storage - local by default, swappable via ImageStorageService
AI_VISION_STORAGE_BACKEND = os.getenv("AI_VISION_STORAGE_BACKEND", "local")  # local | s3 | minio
AI_VISION_IMAGE_DIR = os.getenv("AI_VISION_IMAGE_DIR", "uploads/ai_vision")
AI_VISION_IMAGE_URL = os.getenv("AI_VISION_IMAGE_URL", "/static/ai_vision")

Path(AI_VISION_IMAGE_DIR).mkdir(parents=True, exist_ok=True)
