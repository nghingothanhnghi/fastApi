# app/ai_vision/ai/inference/detector.py
import numpy as np
from typing import Dict, Any
from app.ai_vision.ai.base.vision_model import PlantVisionModel


class MockYOLOPlantDetector(PlantVisionModel):
    """Placeholder detector. Swap this for a real Ultralytics YOLO model
    (see app/camera_object_detection/controllers/detector.py for the
    existing YOLO-loading pattern already used elsewhere in this repo)
    without changing anything downstream - InferenceManager only depends
    on `predict()`'s return shape."""

    name = "plant-detector"
    version = "v1-mock"
    task = "detection"

    def predict(self, image: np.ndarray) -> Dict[str, Any]:
        h, w = image.shape[:2]
        # Deterministic-ish placeholder so growth tracking has *something*
        # consistent to diff against until a real model is plugged in.
        canopy_area_px = float((image.mean() / 255.0) * (h * w) * 0.4)
        return {
            "confidence": 0.75,
            "bbox": [0, 0, w, h],
            "canopy_area_px": canopy_area_px,
            "leaf_count": None,  # unreliable without a real model - report None, not a guess
            "image_width": w,
            "image_height": h,
        }
