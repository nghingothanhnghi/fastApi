# app/ai_vision/models/plant_health.py
from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, JSON, func
from app.database import Base


class PlantHealthRecord(Base):
    __tablename__ = "ai_vision_health_records"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("ai_vision_plants.id"), nullable=False, index=True)
    image_id = Column(Integer, ForeignKey("ai_vision_images.id"), nullable=True)

    health_score = Column(Integer, nullable=False)  # 0-100
    status = Column(String(20), nullable=False, index=True)
    # healthy | normal | attention | warning | critical | unknown

    visual_indicators = Column(JSON, nullable=True)   # ["leaf_yellowing", "canopy_reduction"]
    possible_issues = Column(JSON, nullable=True)      # [{"issue": "...", "confidence": 0.7}]
    sensor_snapshot = Column(JSON, nullable=True)      # {"ph": 6.1, "ec": 1.8, "temperature": 27.2, ...}

    confidence = Column(Float, nullable=True)
    model_name = Column(String(100), nullable=True)
    model_version = Column(String(30), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
