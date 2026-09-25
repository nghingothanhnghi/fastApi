import os
from uuid import uuid4
import cv2
from app.ai_vision import config


def save_annotated_image(image, predictions_by_task: dict) -> str | None:
    """Draw the detection bbox + health/disease indicators onto a copy of
    the image, save it next to the original, and return its public URL."""
    if image is None:
        return None

    annotated = image.copy()

    detection = predictions_by_task.get("detection")
    if detection and detection.raw_output.get("bbox"):
        x1, y1, x2, y2 = [int(v) for v in detection.raw_output["bbox"]]
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
        conf = detection.confidence or 0
        cv2.putText(annotated, f"plant {conf:.2f}", (x1, max(y1 - 8, 0)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    health = predictions_by_task.get("health")
    if health:
        indicators = health.raw_output.get("visual_indicators") or ["healthy"]
        cv2.putText(annotated, ", ".join(indicators), (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    disease = predictions_by_task.get("disease")
    if disease and disease.raw_output.get("visual_indicators"):
        cv2.putText(annotated, ", ".join(disease.raw_output["visual_indicators"]),
                    (10, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 140, 255), 2)

    filename = f"{uuid4().hex}_annotated.jpg"
    file_path = os.path.join(config.AI_VISION_IMAGE_DIR, filename)
    cv2.imwrite(file_path, annotated)

    return f"{config.AI_VISION_IMAGE_URL.rstrip('/')}/{filename}"