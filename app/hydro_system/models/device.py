# app/hydro_system/models/device.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func, Boolean
from sqlalchemy.orm import relationship
from app.database import Base

class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)  # e.g., "Greenhouse Pump Controller"

    device_id = Column(String, unique=True, nullable=False)  # ESP32 unique ID (e.g., MAC or UUID)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="devices")
    client_id = Column(String, nullable=True)

    location = Column(String, nullable=True)  # e.g., "Greenhouse A"
    type = Column(String, nullable=True)  # e.g., "pump", "sensor", etc.
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


