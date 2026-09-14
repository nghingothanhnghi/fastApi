# app/ai_vision/integrations/camera_client.py
import numpy as np
import cv2
from typing import Optional
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def load_image_from_path(storage_path: str) -> Optional[np.ndarray]:
    img = cv2.imread(storage_path)
    if img is None:
        logger.error(f"Could not decode image at {storage_path}")
    return img


def fetch_image_from_camera(stream_url: str) -> Optional[np.ndarray]:
    """Stub for pulling a single frame from an ESP32-CAM/IP camera snapshot
    endpoint. Wire this up the same way app/android_system's device_manager
    talks to hardware - i.e. behind a client object, mockable via a
    USE_MOCK_DEVICES-style flag, once real camera hardware is available."""
    raise NotImplementedError("Live camera pull not wired up yet - use image upload for now")
