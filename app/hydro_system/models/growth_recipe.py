# app/hydro_system/models/growth_recipe.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Time
from datetime import datetime
from sqlalchemy.orm import relationship
from app.database import Base


class GrowthRecipe(Base):
    __tablename__ = "growth_recipes"

    id = Column(Integer, primary_key=True)
    stage_id = Column(Integer, ForeignKey("growth_stages.id", ondelete="CASCADE"))
    stage = relationship("GrowthStage", back_populates="recipes")

    actuator_type = Column(String, nullable=False)  # light, pump, ...

    # Optional targeting (NULL/NULL = every actuator of actuator_type)
    group_name = Column(String(50), nullable=True)
    actuator_id = Column(Integer, ForeignKey("hydro_actuators.id"), nullable=True)

    action = Column(String, nullable=False)         # on, interval

    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)

    interval_on_min = Column(Integer, nullable=True)
    interval_off_min = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)