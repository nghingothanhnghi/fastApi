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

    # Hardware mapping
    pin = Column(String, nullable=True)    # "26", "27" pin GPIO.
    port = Column(Integer, nullable=False) # logical port (optional)

    # Control
    is_active = Column(Boolean, default=True)  # For logical control
    default_state = Column(Boolean, default=False)  # Initial state (optional)

    control_mode = Column(
        String,
        default="binary"   # binary | pulse | pwm
    )

    control_params = Column(
        JSON,
        nullable=True
        # Examples:
        # pulse: { "on_ms": 3000, "off_ms": 10000 }
        # pwm:   { "duty": 70, "freq": 1000 }
    )    

    device_id = Column(Integer, ForeignKey("devices_hydro.id"), nullable=False)
    device = relationship("HydroDevice", back_populates="actuators")

    logs = relationship("HydroActuatorLog", back_populates="actuator", cascade="all, delete")
    schedules = relationship("HydroSchedule", back_populates="actuator", cascade="all, delete")

    sensor_key = Column(String, nullable=True)
    manual_state = Column(Boolean, nullable=True, default=None)  # True (Force ON), False (Force OFF), None (Auto)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
