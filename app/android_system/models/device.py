# backend/app/android_system/models/device.py
# This file defines the SQLAlchemy model for Android devices in the system.
# It includes fields for device serial, name, status, properties, and timestamps.

from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON
from app.database import Base
from datetime import datetime

class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    serial = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    status = Column(String, default="unknown")  # online, offline, unauthorized, unknown
    is_mock = Column(Boolean, default=False)
    
    # Device properties stored as JSON
    properties = Column(JSON, nullable=True)
    
    # Connection info
    last_seen = Column(DateTime, default=datetime.utcnow)
    connection_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        """Convert device to dictionary representation"""
        return {
            "id": self.id,
            "serial": self.serial,
            "name": self.name,
            "status": self.status,
            "is_mock": self.is_mock,
            "properties": self.properties or {},
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "connection_count": self.connection_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }