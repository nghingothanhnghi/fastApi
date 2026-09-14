# app/ai_vision/ai/inference/classifier.py
import numpy as np
from typing import Dict, Any
from app.ai_vision.ai.base.vision_model import PlantVisionModel


class MockLeafHealthClassifier(PlantVisionModel):
    name = "plant-health"
    version = "v1-mock"
    task = "health"

    def predict(self, image: np.ndarray) -> Dict[str, Any]:
        # Placeholder color heuristic: greener average pixel -> healthier.
        # Replace with a trained classifier's output; keep the same keys.
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
