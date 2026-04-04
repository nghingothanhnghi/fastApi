# app/hydro_system/models/growth_recipe.py
# GrowthRecipe model representing the recipe for a growth stage in the hydroponic system
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func, Boolean, JSON, Float, Time
from datetime import datetime
from sqlalchemy.orm import relationship
from app.database import Base

class GrowthRecipe(Base):
    __tablename__ = "growth_recipes"

    id = Column(Integer, primary_key=True)
    stage_id = Column(Integer, ForeignKey("growth_stages.id", ondelete="CASCADE"))
    stage = relationship("GrowthStage", back_populates="recipes")

    actuator_type = Column(String, nullable=False)  # light, pump
    action = Column(String, nullable=False)         # on, interval

    # ⏱ Time-based control (for schedules)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)

    # 🔁 Interval control (for pumps)
    interval_on_min = Column(Integer, nullable=True)
    interval_off_min = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)