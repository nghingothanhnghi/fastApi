# app/ai_vision/ai/inference/disease_classifier.py
import numpy as np
import cv2
from typing import Dict, Any
from app.ai_vision.ai.base.vision_model import PlantVisionModel


class LeafDiseasePestClassicalCV(PlantVisionModel):
    """
    V3: disease/pest signal from classical computer vision - NOT a trained
    disease/pest classifier. No labeled dataset (e.g. PlantVillage disease
    categories, or insect-damage imagery) was available to train one here.
    Instead this detects two real, well-established visual proxies:

    1. Leaf-edge damage (pest chewing / physical damage): "solidity" - the
       ratio of the vegetation contour's area to its convex-hull area. An
       intact leaf silhouette is close to convex (solidity near 1.0);
       chewed or torn edges introduce concavities that lower it.
    2. Leaf-spot disease (fungal/bacterial lesions): dark, low-value blobs
       found *inside* the vegetation region, counted via contour detection.

    Known limitation: this runs on the full uploaded frame, like the health
    classifier - it is not yet cropped to the detector's plant bounding box,
    so a busy background can dilute the signal. Wiring the detector's bbox
    through to this task is a natural follow-up once the pipeline supports
    passing intermediate results between tasks (currently each task runs
    independently on the same frame - see vision_service.run_predictions).

    Thresholds below are conservative starting points, not calibrated
    against labeled data - treat as a baseline to tune once real
    disease/pest photos are available.
    """

    name = "leaf-disease-pest-cv"
    version = "v1-cv"
    task = "disease"

    _GREEN = (np.array([25, 30, 30]), np.array([95, 255, 255]))
    _MIN_LEAF_AREA_PX = 400            # ignore tiny/noisy vegetation blobs
    _SOLIDITY_DAMAGE_THRESHOLD = 0.85
    _SPOT_MIN_AREA_PX = 8
    _SPOT_MAX_AREA_RATIO = 0.05        # a "spot" should be small relative to the leaf
    _SPOT_COUNT_INDICATOR = 3
    _SPOT_AREA_RATIO_INDICATOR = 0.015

    def predict(self, image: np.ndarray) -> Dict[str, Any]:
        if image is None or image.size == 0:
            return self._empty_result()

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        veg_mask = cv2.inRange(hsv, *self._GREEN)

        contours, _ = cv2.findContours(veg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        leaf_contour = max(contours, key=cv2.contourArea) if contours else None

        if leaf_contour is None or cv2.contourArea(leaf_contour) < self._MIN_LEAF_AREA_PX:
            return self._empty_result(confidence=0.2)

        leaf_area = cv2.contourArea(leaf_contour)
        hull = cv2.convexHull(leaf_contour)
        hull_area = cv2.contourArea(hull) or leaf_area
        solidity = float(leaf_area / hull_area) if hull_area else 1.0

        leaf_mask = np.zeros(veg_mask.shape, dtype=np.uint8)
        cv2.drawContours(leaf_mask, [leaf_contour], -1, 255, thickness=cv2.FILLED)

        value_channel = hsv[:, :, 2]
        # Dark spots that fall inside the leaf silhouette
        dark_mask = cv2.bitwise_and(cv2.inRange(value_channel, 0, 90), leaf_mask)

        spot_contours, _ = cv2.findContours(dark_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        valid_spots = [
            c for c in spot_contours
            if self._SPOT_MIN_AREA_PX <= cv2.contourArea(c) <= leaf_area * self._SPOT_MAX_AREA_RATIO
        ]
        spot_area = sum(cv2.contourArea(c) for c in valid_spots)
        spot_area_ratio = float(spot_area / leaf_area) if leaf_area else 0.0
        spot_count = len(valid_spots)

        visual_indicators = []
        possible_issues = []

        if solidity < self._SOLIDITY_DAMAGE_THRESHOLD:
            visual_indicators.append("leaf_edge_damage")
            possible_issues.append({
                "issue": "possible_pest_damage",
                "confidence": round(min((1 - solidity) * 3, 0.9), 2),
            })

        if spot_count >= self._SPOT_COUNT_INDICATOR or spot_area_ratio >= self._SPOT_AREA_RATIO_INDICATOR:
            visual_indicators.append("leaf_spots")
            possible_issues.append({
                "issue": "possible_fungal_or_bacterial_leaf_spot",
                "confidence": round(min(spot_area_ratio * 20 + spot_count * 0.05, 0.9), 2),
            })

        confidence = round(min(0.5 + (leaf_area / (image.shape[0] * image.shape[1])), 0.9), 2)

        return {
            "confidence": confidence,
            "leaf_solidity": round(solidity, 3),
            "spot_count": spot_count,
            "spot_area_ratio": round(spot_area_ratio, 4),
            "visual_indicators": visual_indicators,
            "possible_issues": possible_issues,
        }

    @staticmethod
    def _empty_result(confidence: float = 0.0) -> Dict[str, Any]:
        return {
            "confidence": confidence,
            "leaf_solidity": None,
            "spot_count": 0,
            "spot_area_ratio": 0.0,
            "visual_indicators": [],
            "possible_issues": [],
        }


class MockDiseasePestClassifier(PlantVisionModel):
    """Fallback used when AI_USE_REAL_MODELS=false or real-model loading fails."""

    name = "disease-pest-classifier"
    version = "v1-mock"
    task = "disease"

    def predict(self, image: np.ndarray) -> Dict[str, Any]:
        return {
            "confidence": 0.5,
            "leaf_solidity": 0.95,
            "spot_count": 0,
            "spot_area_ratio": 0.0,
            "visual_indicators": [],
            "possible_issues": [],
        }
