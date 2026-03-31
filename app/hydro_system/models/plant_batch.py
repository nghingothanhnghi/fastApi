from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func, Boolean, JSON, Date
from datetime import datetime
from sqlalchemy.orm import relationship
from app.database import Base

class PlantBatch(Base):
    __tablename__ = "plant_batches"

    id = Column(Integer, primary_key=True)
    plant_id = Column(Integer, ForeignKey("plants.id"))
    zone_id = Column(Integer, nullable=True)  # link later

    start_date = Column(Date, nullable=False)
    status = Column(String(20), default="growing")

    created_at = Column(DateTime, default=datetime.utcnow)