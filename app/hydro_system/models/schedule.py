# app/hydro_system/models/schedule.py

from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, func, Time
from sqlalchemy.orm import relationship
from app.database import Base

class HydroSchedule(Base):
    __tablename__ = "hydro_schedules"

    id = Column(Integer, primary_key=True, index=True)
    actuator_id = Column(Integer, ForeignKey("hydro_actuators.id"), nullable=False)
    
    # Schedule times
    start_time = Column(Time, nullable=False)  # Example: 08:00:00
    end_time = Column(Time, nullable=False)    # Example: 20:00:00
    
    # Comma-separated days (e.g., "mon,tue,wed,thu,fri,sat,sun")
    repeat_days = Column(String, nullable=False, default="mon,tue,wed,thu,fri,sat,sun")
    
    is_active = Column(Boolean, default=True)

    # Relationships
    actuator = relationship("HydroActuator", back_populates="schedules")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
