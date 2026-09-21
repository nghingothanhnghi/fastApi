# app/ai_vision/ai/inference/inference_manager.py
import time
import numpy as np
from typing import Dict, Any, List
from app.ai_vision.ai.inference.detector import YOLOPlantDetector, MockYOLOPlantDetector
from app.ai_vision.ai.inference.classifier import HSVLeafHealthClassifier, MockLeafHealthClassifier
from app.ai_vision.ai.inference.disease_classifier import LeafDiseasePestClassicalCV, MockDiseasePestClassifier
from app.ai_vision.ai.base.vision_model import PlantVisionModel
from app.ai_vision import config
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def _build_registry() -> Dict[str, PlantVisionModel]:
    """
    Build the real model registry: V2 Ultralytics YOLO detector + HSV
    classical-CV health classifier, plus the V3 classical-CV disease/pest
    detector, when config.AI_USE_REAL_MODELS is set.

    Falls back to the V1 mocks automatically if any real model fails to
    load (e.g. ultralytics/torch/opencv missing, or weights can't be
    downloaded) so a misconfigured environment degrades gracefully instead
    of crashing the whole module at import time.
    """
    if config.AI_USE_REAL_MODELS:
        try:
            registry = {
                "detection": YOLOPlantDetector(),
                "health": HSVLeafHealthClassifier(),
                "disease": LeafDiseasePestClassicalCV(),
            }
            logger.info(
                "[AIVision] Loaded real models: "
                f"detection={registry['detection'].name}/{registry['detection'].version}, "
                f"health={registry['health'].name}/{registry['health'].version}, "
                f"disease={registry['disease'].name}/{registry['disease'].version}"
            )
            return registry
        except Exception as e:
            logger.error(
                f"[AIVision] Failed to load real vision models, falling back "
                f"to mocks: {e}",
                exc_info=True,
            )

    logger.warning("[AIVision] Using mock detector/classifier/disease models (AI_USE_REAL_MODELS=false or load failed)")
    return {
        "detection": MockYOLOPlantDetector(),
        "health": MockLeafHealthClassifier(),
        "disease": MockDiseasePestClassifier(),
    }


class InferenceManager:
    """Central place that knows which model version is 'current' for each
    task. Swapping any task's model (a fine-tuned checkpoint, a new
    algorithm) means changing MODEL_REGISTRY / config, not any
    service/router. Every result is timestamped with the exact
    model_name/model_version used, per the model-versioning requirement."""

    MODEL_REGISTRY: Dict[str, PlantVisionModel] = _build_registry()

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
