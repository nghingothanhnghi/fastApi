# app/camera_object_detection/controllers/detector.py

import time
from pathlib import Path
from typing import Dict, Any
import numpy as np
import torch
import cv2
from fastapi import HTTPException
from ultralytics import YOLO

from app.utils.image_processing import encode_image_to_base64
from app.camera_object_detection.config import MODELS_DIR, DEFAULT_MODEL_NAME, YOLO_FALLBACK_MODEL
from app.core.logging_config import get_logger

logger = get_logger(__name__)

model_cache = {}

class ObjectDetector:
    def __init__(self, model_name: str = DEFAULT_MODEL_NAME):
        self.model_name = model_name
        self.model_path = MODELS_DIR / f"{model_name}.pt"
        self.model = None
        self.load_model()
    
    def load_model(self):
        if self.model_name in model_cache:
            self.model = model_cache[self.model_name]
            logger.info(f"Loaded model '{self.model_name}' from cache.")
            return

        try:
            if self.model_path.exists():
                self.model = YOLO(str(self.model_path))
                logger.info(f"Loaded custom model from {self.model_path}")
            else:
                self.model = YOLO(YOLO_FALLBACK_MODEL)
                logger.info("Loaded default yolov5s model")

            model_cache[self.model_name] = self.model
        except Exception as e:
            logger.error(f"Failed to load model '{self.model_name}': {e}")
            raise HTTPException(status_code=500, detail="Model loading failed")

    def detect_objects(self, image: np.ndarray) -> Dict[str, Any]:
        if self.model is None:
            self.load_model()

        start_time = time.time()
        results = self.model(image)
        processing_time = (time.time() - start_time) * 1000

        detections = []
        for box in results[0].boxes.data.cpu().numpy():
            x1, y1, x2, y2, conf, cls = box
            class_name = results[0].names[int(cls)]
            detections.append({
                "class": class_name,
                "confidence": float(conf),
                "bbox": [float(x1), float(y1), float(x2), float(y2)]
            })

        annotated_img = results[0].plot()
        encoded_image = encode_image_to_base64(annotated_img)

        return {
            "detections": detections,
            "annotated_image": encoded_image,
            "processing_time_ms": processing_time,
            "image_size": f"{image.shape[1]} x {image.shape[0]}"
        }


def get_detector(model_name: str = DEFAULT_MODEL_NAME):
    return ObjectDetector(model_name)
