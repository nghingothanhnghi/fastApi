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
        hardware_mapping = self._get_hardware_mapping()
        
        for box in results[0].boxes.data.cpu().numpy():
            x1, y1, x2, y2, conf, cls = box
            class_name = results[0].names[int(cls)]
            
            # Map detected objects to hardware components
            hardware_type = self._map_to_hardware(class_name, hardware_mapping)
            
            detections.append({
                "class_name": hardware_type or class_name,  # Use hardware type if mapped
                "original_class": class_name,  # Keep original for reference
                "confidence": float(conf),
                "bbox": [float(x1), float(y1), float(x2 - x1), float(y2 - y1)],  # Convert to [x, y, width, height]
                "is_hardware": hardware_type is not None
            })

        annotated_img = results[0].plot()
        encoded_image = encode_image_to_base64(annotated_img)

        return {
            "detections": detections,
            "annotated_image": encoded_image,
            "processing_time_ms": processing_time,
            "image_size": f"{image.shape[1]} x {image.shape[0]}"
        }
    
    def _get_hardware_mapping(self) -> Dict[str, str]:
        """Map common objects to hardware components using the existing service mapping"""
        from app.camera_object_detection.services.hardware_detection_service import HardwareDetectionService
        
        # Get the existing hardware mapping and extend it with common object mappings
        base_mapping = HardwareDetectionService.HARDWARE_TYPE_MAPPING.copy()
        
        # Add mappings for common objects that might represent hardware
        extended_mapping = {
            # Electronics and devices
            "laptop": "controller",
            "cell phone": "sensor", 
            "mouse": "controller",
            "keyboard": "controller",
            "remote": "controller",
            "clock": "sensor",
            
            # Containers and vessels that might be tanks/reservoirs
            "bottle": "tank",
            "cup": "tank",
            "bowl": "tank",
            "vase": "tank",
            "bucket": "tank",
            
            # Tools and equipment
            "scissors": "tool",
            "knife": "tool",
            
            # Lighting systems
            "tv": "light",
            
            # Plants and growing (crops)
            "potted plant": "plant",
            "broccoli": "plant",
            "carrot": "plant", 
            "apple": "plant",
            "orange": "plant",
            "banana": "plant",
            
            # Appliances that might represent hardware
            "toaster": "relay",
            "microwave": "controller",
            "refrigerator": "pump",
            "oven": "relay",
            "hair drier": "pump",  # Often looks like small pumps
            "blender": "pump",
            
            # Add more mappings as needed
        }
        
        # Merge the mappings
        base_mapping.update(extended_mapping)
        return base_mapping
    
    def _map_to_hardware(self, class_name: str, hardware_mapping: Dict[str, str]) -> str:
        """Map detected class to hardware component"""
        return hardware_mapping.get(class_name.lower())


def get_detector(model_name: str = DEFAULT_MODEL_NAME):
    return ObjectDetector(model_name)
