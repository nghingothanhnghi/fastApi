# app/hydro_system/models/device.py
# Description: Device model for hydroponic systems
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func, Boolean, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class HydroDevice(Base):
    __tablename__ = "devices_hydro"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)  # e.g., "Greenhouse Pump Controller"

    device_id = Column(String, unique=True, nullable=False)  # ESP32 unique ID (e.g., MAC or UUID)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="devices_hydro")
    client_id = Column(String, nullable=True)

    location = Column(String, nullable=True)  # e.g., "Greenhouse A"
    type = Column(String, nullable=True)  # controller
    is_active = Column(Boolean, default=True)

    # Inside class HydroDevice:
    actuators = relationship("HydroActuator", back_populates="device", cascade="all, delete")


    thresholds = Column(JSON, nullable=True)  # ✅ Per-device automation thresholds

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


