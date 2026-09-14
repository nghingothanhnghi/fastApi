# app/ai_vision/models/plant_anomaly.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, JSON, func
from app.database import Base


class PlantAnomaly(Base):
    __tablename__ = "ai_vision_anomalies"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("ai_vision_plants.id"), nullable=False, index=True)

    anomaly_type = Column(String(50), nullable=False)
    # growth_slowdown | abnormal_water_consumption | abnormal_flow | visual_change | sensor_deviation

    severity = Column(String(20), nullable=False, default="medium")  # low|medium|high
    description = Column(String(500), nullable=True)
    evidence = Column(JSON, nullable=True)   # the numbers that triggered it

    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    is_resolved = Column(Boolean, default=False)

    def __repr__(self):
        return f"<PlantAnomaly(plant_id={self.plant_id}, type={self.anomaly_type}, severity={self.severity})>"
