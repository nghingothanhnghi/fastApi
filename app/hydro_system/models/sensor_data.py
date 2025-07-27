# backend/app/hydro_system/models/sensor_data.py
# This file defines the SQLAlchemy model for sensor data in the hydroponics system.
# It includes fields for temperature, humidity, light, moisture, water_level, and a timestamp for when the data was created.
# It is used to store and retrieve sensor readings from a database.
from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey
from app.database import Base
from datetime import datetime
from sqlalchemy.orm import relationship

class SensorData(Base):
    __tablename__ = "sensor_data"

    id = Column(Integer, primary_key=True, index=True)
    temperature = Column(Float)
    humidity = Column(Float)
    light = Column(Float)
    moisture = Column(Float)
    water_level = Column(Float)  # Water level in percentage (0-100%)
    created_at = Column(DateTime, default=datetime.utcnow)

    device_id = Column(Integer, ForeignKey("devices_hydro.id"), nullable=True)
    device = relationship("HydroDevice")