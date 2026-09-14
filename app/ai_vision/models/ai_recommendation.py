# app/ai_vision/models/ai_recommendation.py
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, func
from app.database import Base


class AIRecommendation(Base):
    __tablename__ = "ai_vision_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("ai_vision_plants.id"), nullable=False, index=True)
    health_record_id = Column(Integer, ForeignKey("ai_vision_health_records.id"), nullable=True)
    anomaly_id = Column(Integer, ForeignKey("ai_vision_anomalies.id"), nullable=True)

    recommendation = Column(String(500), nullable=False)
    reasons = Column(JSON, nullable=False)   # list[str] - must always be non-empty (explainability requirement)
    severity = Column(String(20), nullable=False, default="low")
    confidence = Column(Float, nullable=True)

    # Deliberately never "approved_and_executed" in V1 - see safety boundary in the plan.
    status = Column(String(30), nullable=False, default="pending_review")
    # pending_review | acknowledged | dismissed

    created_at = Column(DateTime(timezone=True), server_default=func.now())
