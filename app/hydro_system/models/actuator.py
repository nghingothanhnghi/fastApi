# app/hydro_system/models/actuator.py

from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, func, JSON
from sqlalchemy.orm import relationship
from app.database import Base
from app.hydro_system.models.device import HydroDevice   

class HydroActuator(Base):
    __tablename__ = "hydro_actuators"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, nullable=False)  # "pump", "light", "fan", etc.
    name = Column(String, nullable=True)   # Optional name like "Grow Light 1"
    pin = Column(String, nullable=True)    # Optional: GPIO pin identifier on ESP32
    port = Column(Integer, nullable=False) # GPIO pin number
    is_active = Column(Boolean, default=True)  # For logical control
    default_state = Column(Boolean, default=False)  # Initial state (optional)

    device_id = Column(Integer, ForeignKey("devices_hydro.id"), nullable=False)
    device = relationship("HydroDevice", back_populates="actuators")

    logs = relationship("HydroActuatorLog", back_populates="actuator", cascade="all, delete")

    sensor_key = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
