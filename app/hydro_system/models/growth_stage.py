# app/hydro_system/models/growth_stage.py
# GrowthStage model representing a stage in the plant growth cycle
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func, Boolean, JSON
from datetime import datetime
from sqlalchemy.orm import relationship
from app.database import Base

class GrowthStage(Base):
    __tablename__ = "growth_stages"

    id = Column(Integer, primary_key=True)
    plant_id = Column(Integer, ForeignKey("plants.id", ondelete="CASCADE"))

    # ✅ NEW — which cultivation plan this stage belongs to. This is now the
    # authoritative scope for stage progression/lookup, since multiple plans
    # can exist for the same plant_id with independent (possibly
    # overlapping) day_start/day_end ranges. plant_id is kept as a
    # denormalized field for convenience/back-compat listing only (same
    # pattern already used by HydroFlowReading.device_id).
    plan_id = Column(Integer, ForeignKey("growth_plans.id", ondelete="CASCADE"), nullable=True)

    name = Column(String(50), nullable=False)
    day_start = Column(Integer, nullable=False)
    day_end = Column(Integer, nullable=False)
    recipes = relationship("GrowthRecipe", back_populates="stage", cascade="all, delete")

    plan = relationship("GrowthPlan", back_populates="stages")

    created_at = Column(DateTime, default=datetime.utcnow)