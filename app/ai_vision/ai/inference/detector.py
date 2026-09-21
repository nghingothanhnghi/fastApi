# app/ai_vision/ai/inference/detector.py
import numpy as np
import cv2
from typing import Dict, Any, Set
from app.ai_vision.ai.base.vision_model import PlantVisionModel
from app.ai_vision import config
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Process-wide cache so repeated inference calls (and repeated
# YOLOPlantDetector() instantiations via InferenceManager) don't reload
# weights from disk every time. Mirrors the model_cache pattern already
# used in app/camera_object_detection/controllers/detector.py.
_model_cache: Dict[str, Any] = {}


def _load_yolo_model(weights: str):
    if weights in _model_cache:
        return _model_cache[weights]
    from ultralytics import YOLO  # local import: keep this module importable
    model = YOLO(weights)         # even if ultralytics/torch aren't installed
    _model_cache[weights] = model
    logger.info(f"[AIVision] Loaded YOLO detector weights: {weights}")
    return model


class YOLOPlantDetector(PlantVisionModel):
    """
    Real object detector (Ultralytics YOLO, COCO-pretrained by default) used
    to locate the plant/canopy region in an uploaded image. It detects the
    "potted plant" class and, within that box, refines a canopy pixel mask
    using an HSV green-vegetation threshold so `canopy_area_px` reflects
    actual green pixels rather than the raw bounding-box area.

    This is a real, general-purpose detector - it is NOT fine-tuned on a
    plant-specific dataset (none was available to train one here). Swapping
    in a fine-tuned checkpoint later is a one-line change
    (`config.AI_DETECTOR_WEIGHTS`); nothing downstream needs to change,
    because the return shape below matches the mock detector it replaces
    exactly (confidence, bbox, canopy_area_px, leaf_count, image_width,
    image_height).
    """

    name = "yolo-plant-detector"
    task = "detection"

    def __init__(self):
        self.model = _load_yolo_model(config.AI_DETECTOR_WEIGHTS)
        self.version = config.AI_DETECTOR_WEIGHTS
        self._plant_class_ids = self._resolve_plant_class_ids()

    def _resolve_plant_class_ids(self) -> Set[int]:
        names = self.model.names  # {id: name}, e.g. {58: "potted plant", ...}
        wanted = {"potted plant", "plant"}
        ids = {i for i, n in names.items() if str(n).lower() in wanted}
        if not ids:
            logger.warning(
                "[AIVision] No 'potted plant' class found in model labels; "
                "detector will consider all detected classes."
            )
        return ids

    def predict(self, image: np.ndarray) -> Dict[str, Any]:
        h, w = image.shape[:2]
        results = self.model(image, verbose=False)
        boxes = results[0].boxes

        best_box = None
        best_conf = 0.0
        for box in boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            if self._plant_class_ids and cls_id not in self._plant_class_ids:
                continue
            if conf > best_conf:
                best_conf = conf
                best_box = box

        if best_box is None:
            # No plant-class detection in frame. Fall back to the full image
            # so growth tracking still has *something* to diff against, but
            # report the low confidence honestly rather than faking a value.
            x1, y1, x2, y2 = 0, 0, w, h
            confidence = 0.0
        else:
            x1, y1, x2, y2 = [int(v) for v in best_box.xyxy[0]]
            confidence = best_conf

        x1c, y1c = max(x1, 0), max(y1, 0)
        x2c, y2c = min(max(x2, x1c + 1), w), min(max(y2, y1c + 1), h)
        crop = image[y1c:y2c, x1c:x2c]

        canopy_area_px = self._green_pixel_area(crop) if crop.size else 0.0

        return {
            "confidence": confidence,
            "bbox": [x1, y1, x2, y2],
            "canopy_area_px": canopy_area_px,
            "leaf_count": None,  # not reliably estimable from bbox + color mask alone
            "image_width": w,
            "image_height": h,
        }

    @staticmethod
    def _green_pixel_area(crop: np.ndarray) -> float:
        """Count pixels that look like live vegetation (HSV green band)
        inside the detected region, as a canopy-size proxy."""
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        lower_green = np.array([25, 30, 30])
        upper_green = np.array([95, 255, 255])
        mask = cv2.inRange(hsv, lower_green, upper_green)
        return float(np.count_nonzero(mask))


class MockYOLOPlantDetector(PlantVisionModel):
    """Kept for local dev / environments without ultralytics+torch installed,
    and as the automatic fallback if real-model loading fails at startup
    (see inference_manager.py)."""

    name = "plant-detector"
    version = "v1-mock"
    task = "detection"

    def predict(self, image: np.ndarray) -> Dict[str, Any]:
        h, w = image.shape[:2]
        canopy_area_px = float((image.mean() / 255.0) * (h * w) * 0.4)
        return {
            "confidence": 0.75,
            "bbox": [0, 0, w, h],
            "canopy_area_px": canopy_area_px,
            "leaf_count": None,
            "image_width": w,
            "image_height": h,
        }
