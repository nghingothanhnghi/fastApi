# app/ai_vision/models/inference_job.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, func
from app.database import Base


class AIInferenceJob(Base):
    __tablename__ = "ai_vision_inference_jobs"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey("ai_vision_images.id"), nullable=False, index=True)
    model_name = Column(String(100), nullable=False)
    model_version = Column(String(30), nullable=False)

    status = Column(String(20), nullable=False, default="queued", index=True)
    # queued | processing | completed | failed
    error_message = Column(Text, nullable=True)

    queued_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<AIInferenceJob(id={self.id}, image_id={self.image_id}, status={self.status})>"
