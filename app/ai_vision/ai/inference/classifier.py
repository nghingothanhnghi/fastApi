# app/ai_vision/ai/inference/classifier.py
import numpy as np
import cv2
from typing import Dict, Any
from app.ai_vision.ai.base.vision_model import PlantVisionModel


class HSVLeafHealthClassifier(PlantVisionModel):
    """
    Real (non-deep-learning) leaf-health signal based on classical computer
    vision: HSV color-band ratios computed over the image's vegetation mask
    (green vs. yellowing vs. browning pixel fractions).

    This is genuine, deterministic image analysis - not a placeholder - but
    it is NOT a trained classifier. Training an actual disease/nutrient
    classifier requires a labeled leaf-image dataset (e.g. PlantVillage)
    that isn't available in this environment. Swap this class for one
    wrapping a trained model later without touching InferenceManager or any
    caller: the return shape below matches the mock classifier it replaces
    exactly (confidence, leaf_color_index, visual_indicators,
    possible_issues).
    """

    name = "hsv-leaf-health"
    version = "v1-cv"
    task = "health"

    # HSV bands (OpenCV convention: H in 0-179, S/V in 0-255)
    _GREEN = (np.array([25, 30, 30]), np.array([95, 255, 255]))
    _YELLOW = (np.array([15, 40, 40]), np.array([34, 255, 255]))
    _BROWN = (np.array([5, 40, 20]), np.array([20, 200, 150]))

    # Thresholds are conservative defaults, not tuned against real labeled
    # data - treat as a starting point to calibrate once real photos are
    # available, not as ground truth.
    _MIN_VEGETATION_RATIO = 0.02
    _YELLOW_INDICATOR_RATIO = 0.15
    _BROWN_INDICATOR_RATIO = 0.08
    _LOW_GREENNESS_INDEX = 0.4

    def predict(self, image: np.ndarray) -> Dict[str, Any]:
        if image is None or image.size == 0:
            return {
                "confidence": 0.0,
                "leaf_color_index": 0.0,
                "visual_indicators": [],
                "possible_issues": [],
            }

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        total_px = image.shape[0] * image.shape[1]

        green_mask = cv2.inRange(hsv, *self._GREEN)
        yellow_mask = cv2.inRange(hsv, *self._YELLOW)
        brown_mask = cv2.inRange(hsv, *self._BROWN)

        green_ratio = float(np.count_nonzero(green_mask)) / total_px
        yellow_ratio = float(np.count_nonzero(yellow_mask)) / total_px
        brown_ratio = float(np.count_nonzero(brown_mask)) / total_px

        vegetation_ratio = green_ratio + yellow_ratio + brown_ratio
        # Fraction of "vegetation-colored" pixels that are still green.
        leaf_color_index = (
            green_ratio / vegetation_ratio if vegetation_ratio > 0 else 0.0
        )

        visual_indicators = []
        possible_issues = []

        # Only judge color health if there's actually enough plant material
        # visible - avoids flagging "yellowing" on a near-empty/background
        # frame where color ratios are dominated by noise.
        if vegetation_ratio > self._MIN_VEGETATION_RATIO:
            if yellow_ratio > self._YELLOW_INDICATOR_RATIO and yellow_ratio > green_ratio * 0.5:
                visual_indicators.append("leaf_yellowing")
                possible_issues.append({
                    "issue": "possible_nutrient_deficiency",
                    "confidence": round(min(yellow_ratio * 2, 0.9), 2),
                })
            if brown_ratio > self._BROWN_INDICATOR_RATIO:
                visual_indicators.append("leaf_browning")
                possible_issues.append({
                    "issue": "possible_leaf_burn_or_disease",
                    "confidence": round(min(brown_ratio * 3, 0.9), 2),
                })
            if leaf_color_index < self._LOW_GREENNESS_INDEX:
                visual_indicators.append("low_canopy_greenness")

        # Confidence in this reading scales with how much vegetation is
        # actually visible in frame - a near-empty crop gives a weak signal,
        # reported honestly rather than a fixed constant.
        confidence = (
            round(min(0.5 + vegetation_ratio, 0.95), 2)
            if vegetation_ratio > 0.01 else 0.2
        )

        return {
            "confidence": confidence,
            "leaf_color_index": round(leaf_color_index, 3),
            "visual_indicators": visual_indicators,
            "possible_issues": possible_issues,
            "vegetation_ratio": round(vegetation_ratio, 3),
        }


class MockLeafHealthClassifier(PlantVisionModel):
    """Kept for local dev / environments without opencv installed, and as
    the automatic fallback if real-model loading fails at startup (see
    inference_manager.py)."""

    name = "plant-health"
    version = "v1-mock"
    task = "health"

    def predict(self, image: np.ndarray) -> Dict[str, Any]:
        avg_bgr = image.reshape(-1, 3).mean(axis=0) if image.ndim == 3 else [0, 0, 0]
        green_ratio = float(avg_bgr[1] / (sum(avg_bgr) + 1e-6))

        visual_indicators = []
        if green_ratio < 0.30:
            visual_indicators.append("leaf_yellowing")

        return {
            "confidence": 0.65,
            "leaf_color_index": green_ratio,
            "visual_indicators": visual_indicators,
            "possible_issues": (
                [{"issue": "possible_nutrient_deficiency", "confidence": 0.4}]
                if "leaf_yellowing" in visual_indicators else []
            ),
        }
