# app/ai_vision/ai/base/vision_model.py
from abc import ABC, abstractmethod
from typing import Dict, Any
import numpy as np


class PlantVisionModel(ABC):
    """Every AI model (detector, health classifier, disease classifier...)
    implements this so InferenceManager can swap versions without touching
    any caller. Never call this directly from a router - go through
    InferenceManager so model_name/model_version get recorded consistently."""

    name: str
    version: str
    task: str  # "detection" | "health" | "growth" | "disease"

    @abstractmethod
    def predict(self, image: np.ndarray) -> Dict[str, Any]:
        """Return a JSON-serializable dict. Must include a 'confidence' key."""
        raise NotImplementedError
