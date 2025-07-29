# app/hydro_system/models/actuator_log.py

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class HydroActuatorLog(Base):
    __tablename__ = "hydro_actuator_logs"

    id = Column(Integer, primary_key=True, index=True)
    actuator_id = Column(Integer, ForeignKey("hydro_actuators.id"), nullable=False)
    action = Column(String, nullable=False)  # e.g., "on", "off", "toggle"
    state = Column(String, nullable=True)    # Optional: "ON", "OFF", "AUTO"
    source = Column(String, nullable=True)   # "user", "system", "scheduler", "rule_engine"
    note = Column(String, nullable=True)     # Optional note or reason for log

    timestamp = Column(DateTime, default=datetime.utcnow)

    actuator = relationship("HydroActuator", back_populates="logs")
