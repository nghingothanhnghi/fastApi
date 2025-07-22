# app/camera_object_detection/config.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

MODELS_DIR = Path(os.getenv("CUSTOM_MODEL_DIR", "app/models/custom_objects"))
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Default values
DEFAULT_MODEL_NAME = "default"
YOLO_FALLBACK_MODEL = "yolov5s.pt"  # or 'yolov8n.pt' depending on your project