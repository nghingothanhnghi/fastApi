# app/ai_vision/ai/inference/inference_manager.py
import time
import numpy as np
from typing import Dict, Any, List
from app.ai_vision.ai.inference.detector import MockYOLOPlantDetector
from app.ai_vision.ai.inference.classifier import MockLeafHealthClassifier
from app.ai_vision.ai.base.vision_model import PlantVisionModel
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class InferenceManager:
    """Central place that knows which model version is 'current' for each
    task. Swapping plant-detector v1 -> v2 means changing MODEL_REGISTRY,
    not any service/router. Every result is timestamped with the exact
    model_name/model_version used, per the model-versioning requirement."""

    MODEL_REGISTRY: Dict[str, PlantVisionModel] = {
        "detection": MockYOLOPlantDetector(),
        "health": MockLeafHealthClassifier(),
    }

    def run(self, task: str, image: np.ndarray) -> Dict[str, Any]:
        model = self.MODEL_REGISTRY.get(task)
        if not model:
            raise ValueError(f"No model registered for task '{task}'")

        start = time.time()
        output = model.predict(image)
        elapsed_ms = (time.time() - start) * 1000

        return {
            "model_name": model.name,
            "model_version": model.version,
            "task": task,
            "inference_time_ms": elapsed_ms,
            "confidence": output.get("confidence"),
            "raw_output": output,
        }

    def run_all(self, tasks: List[str], image: np.ndarray) -> List[Dict[str, Any]]:
        return [self.run(task, image) for task in tasks]


inference_manager = InferenceManager()
