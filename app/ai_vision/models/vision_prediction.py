# app/ai_vision/models/vision_prediction.py
from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, JSON, func
from app.database import Base


class VisionPrediction(Base):
    """Raw model output for one image. One image can have multiple predictions
    (e.g. a detector run and a health-classifier run)."""
    __tablename__ = "ai_vision_predictions"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey("ai_vision_images.id"), nullable=False, index=True)
    plant_id = Column(Integer, ForeignKey("ai_vision_plants.id"), nullable=False, index=True)

    model_name = Column(String(100), nullable=False)
    model_version = Column(String(30), nullable=False)
    task = Column(String(30), nullable=False)  # detection | health | growth

    confidence = Column(Float, nullable=True)
    inference_time_ms = Column(Float, nullable=True)

    # Structured, model-agnostic payload, e.g.
    # {"bbox": [...], "canopy_area_px": 41233, "leaf_color_index": 0.62, "damaged_regions": []}
    raw_output = Column(JSON, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
