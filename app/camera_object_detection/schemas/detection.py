# backend/app/camera_object_detection/schemas/detection.py
# This file defines the Pydantic schemas for object detection results.

from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime


class DetectionObjectSchema(BaseModel):
    class_name: str
    confidence: float
    bbox_x1: float
    bbox_y1: float
    bbox_x2: float
    bbox_y2: float
    bbox_width: Optional[float] = None
    bbox_height: Optional[float] = None
    bbox_area: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


class DetectionResultSchema(BaseModel):
    id: int
    model_name: str
    image_source: str
    image_filename: Optional[str] = None
    image_size: Optional[str] = None
    detections: List[Dict[str, Any]]
    detection_count: int
    confidence_threshold: Optional[float] = None
    processing_time_ms: Optional[float] = None
    annotated_image: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DetectionResultWithObjectsSchema(DetectionResultSchema):
    detection_objects: List[DetectionObjectSchema] = []

    class Config:
        from_attributes = True


class DetectionStatsSchema(BaseModel):
    total_detections: int
    unique_models: int
    most_common_class: Optional[str] = None
    average_confidence: Optional[float] = None
    detections_by_model: Dict[str, int]
    detections_by_class: Dict[str, int]
    recent_detections: int  # Last 24 hours


class DetectionFilterSchema(BaseModel):
    model_name: Optional[str] = None
    class_name: Optional[str] = None
    min_confidence: Optional[float] = None
    max_confidence: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: Optional[int] = 100
    offset: Optional[int] = 0