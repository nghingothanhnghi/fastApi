# app/hydro_system/models/flow_reading.py
# Flow sensor readings, scoped per actuator (a device can have multiple pumps,
# each with its own flow sensor). device_id is denormalized here so we can
# query "all flow readings at this device / this location" without a join
# through hydro_actuators every time.

from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base


class HydroFlowReading(Base):
    __tablename__ = "hydro_flow_readings"

    id = Column(Integer, primary_key=True, index=True)

    actuator_id = Column(Integer, ForeignKey("hydro_actuators.id"), nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("devices_hydro.id"), nullable=False, index=True)

    flow_rate = Column(Float, nullable=False)  # L/min

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    actuator = relationship("HydroActuator")
    device = relationship("HydroDevice")

    def __repr__(self):
        return f"<HydroFlowReading(actuator_id={self.actuator_id}, flow={self.flow_rate})>"