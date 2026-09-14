# app/ai_vision/models/plant_growth.py
from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, func
from app.database import Base


class PlantGrowthRecord(Base):
    __tablename__ = "ai_vision_growth_records"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("ai_vision_plants.id"), nullable=False, index=True)
    image_id = Column(Integer, ForeignKey("ai_vision_images.id"), nullable=True)

    canopy_area_px = Column(Float, nullable=True)
    estimated_size_cm2 = Column(Float, nullable=True)
    leaf_count = Column(Integer, nullable=True)

    growth_pct_since_last = Column(Float, nullable=True)   # vs the previous record for this plant
    growth_rate_pct_per_day = Column(Float, nullable=True)
    baseline_growth_rate_pct_per_day = Column(Float, nullable=True)
    deviation_from_baseline_pct = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
