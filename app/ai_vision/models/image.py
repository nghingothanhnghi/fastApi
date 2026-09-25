# app/ai_vision/models/image.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from app.database import Base


class PlantImage(Base):
    __tablename__ = "ai_vision_images"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("ai_vision_plants.id"), nullable=False, index=True)
    camera_id = Column(Integer, ForeignKey("ai_vision_cameras.id"), nullable=True)

    storage_path = Column(String(500), nullable=False)   # relative/backend key, never a full-res DB blob
    public_url = Column(String(500), nullable=True)
    annotated_url = Column(String(500), nullable=True)
    image_hash = Column(String(64), nullable=True, index=True)  # sha256, for de-dupe
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    content_type = Column(String(50), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)

    processing_status = Column(String(20), nullable=False, default="uploaded", index=True)
    # uploaded -> queued -> processing -> completed -> failed

    captured_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<PlantImage(id={self.id}, plant_id={self.plant_id}, status={self.processing_status})>"
