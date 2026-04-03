from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func, Boolean, JSON
from datetime import datetime
from sqlalchemy.orm import relationship
from app.database import Base

class GrowthStage(Base):
    __tablename__ = "growth_stages"

    id = Column(Integer, primary_key=True)
    plant_id = Column(Integer, ForeignKey("plants.id", ondelete="CASCADE"))

    name = Column(String(50), nullable=False)
    day_start = Column(Integer, nullable=False)
    day_end = Column(Integer, nullable=False)
    recipes = relationship("GrowthRecipe", back_populates="stage", cascade="all, delete")

    created_at = Column(DateTime, default=datetime.utcnow)