# app/hydro_system/models/growth_plan.py
# GrowthPlan model — a named cultivation-plan variant for a Plant
# (e.g. "Summer Plan", "Indoor Plan", "NFT Plan"). Each plan owns its own
# GrowthStage timeline, so the same Plant can have multiple independent
# stage/recipe timelines, selected per PlantBatch via PlantBatch.plan_id.
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func, Boolean, Text
from sqlalchemy.orm import relationship
from app.database import Base


class GrowthPlan(Base):
    __tablename__ = "growth_plans"

    id = Column(Integer, primary_key=True)
    plant_id = Column(Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(100), nullable=False)  # e.g. "Summer Plan", "Indoor Plan", "NFT Plan"
    description = Column(Text, nullable=True)

    # The plan used when a PlantBatch doesn't explicitly specify one.
    # Exactly one plan per plant should be marked default; enforced in
    # growth_plan_service (not at the DB level, keeping this additive/simple).
    is_default = Column(Boolean, default=False, nullable=False)

    plant = relationship("Plant")
    stages = relationship("GrowthStage", back_populates="plan", cascade="all, delete")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<GrowthPlan(id={self.id}, plant_id={self.plant_id}, name={self.name!r}, default={self.is_default})>"