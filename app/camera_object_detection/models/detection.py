# backend/app/camera_object_detection/models/detection.py
# This file defines the Pydantic schemas for object detection results.

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON
from sqlalchemy.sql import func
from app.database import Base


class DetectionResult(Base):
    __tablename__ = "detection_results"
    
    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String(100), nullable=False, default="default")
    image_source = Column(String(50), nullable=False)  # 'upload', 'base64', 'websocket'
    image_filename = Column(String(255), nullable=True)  # Original filename if uploaded
    image_size = Column(String(20), nullable=True)  # "width x height"
    
    # Detection results as JSON
    detections = Column(JSON, nullable=False)  # Array of detection objects
    detection_count = Column(Integer, nullable=False, default=0)
    
    # Processing metadata
    confidence_threshold = Column(Float, nullable=True)
    processing_time_ms = Column(Float, nullable=True)
    
    # Base64 encoded annotated image (optional - can be large)
    annotated_image = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<DetectionResult(id={self.id}, model={self.model_name}, count={self.detection_count})>"


class DetectionObject(Base):
    __tablename__ = "detection_objects"
    
    id = Column(Integer, primary_key=True, index=True)
    detection_result_id = Column(Integer, nullable=False, index=True)
    
    # Object details
    class_name = Column(String(100), nullable=False)
    confidence = Column(Float, nullable=False)
    
    # Bounding box coordinates
    bbox_x1 = Column(Float, nullable=False)
    bbox_y1 = Column(Float, nullable=False)
    bbox_x2 = Column(Float, nullable=False)
    bbox_y2 = Column(Float, nullable=False)
    
    # Calculated properties
    bbox_width = Column(Float, nullable=True)
    bbox_height = Column(Float, nullable=True)
    bbox_area = Column(Float, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<DetectionObject(id={self.id}, class={self.class_name}, conf={self.confidence:.2f})>"