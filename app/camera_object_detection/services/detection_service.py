from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import time

from ..models.detection import DetectionResult, DetectionObject
from ..schemas.detection import DetectionFilterSchema, DetectionStatsSchema


class DetectionService:
    
    @staticmethod
    def save_detection_result(
        db: Session,
        model_name: str,
        image_source: str,
        detections: List[Dict[str, Any]],
        image_filename: Optional[str] = None,
        image_size: Optional[str] = None,
        confidence_threshold: Optional[float] = None,
        processing_time_ms: Optional[float] = None,
        annotated_image: Optional[str] = None,
        save_individual_objects: bool = True
    ) -> DetectionResult:
        """
        Save detection results to database
        
        Args:
            db: Database session
            model_name: Name of the model used
            image_source: Source of image ('upload', 'base64', 'websocket')
            detections: List of detection dictionaries
            image_filename: Original filename if uploaded
            image_size: Image dimensions as "width x height"
            confidence_threshold: Confidence threshold used
            processing_time_ms: Processing time in milliseconds
            annotated_image: Base64 encoded annotated image
            save_individual_objects: Whether to save individual detection objects
            
        Returns:
            DetectionResult: Saved detection result
        """
        
        # Create main detection result
        detection_result = DetectionResult(
            model_name=model_name,
            image_source=image_source,
            image_filename=image_filename,
            image_size=image_size,
            detections=detections,
            detection_count=len(detections),
            confidence_threshold=confidence_threshold,
            processing_time_ms=processing_time_ms,
            annotated_image=annotated_image
        )
        
        db.add(detection_result)
        db.commit()
        db.refresh(detection_result)
        
        # Save individual detection objects if requested
        if save_individual_objects:
            for detection in detections:
                bbox = detection.get("bbox", [])
                if len(bbox) >= 4:
                    x1, y1, x2, y2 = bbox[:4]
                    width = x2 - x1
                    height = y2 - y1
                    area = width * height
                    
                    detection_object = DetectionObject(
                        detection_result_id=detection_result.id,
                        class_name=detection.get("class", "unknown"),
                        confidence=detection.get("confidence", 0.0),
                        bbox_x1=x1,
                        bbox_y1=y1,
                        bbox_x2=x2,
                        bbox_y2=y2,
                        bbox_width=width,
                        bbox_height=height,
                        bbox_area=area
                    )
                    db.add(detection_object)
            
            db.commit()
        
        return detection_result
    
    @staticmethod
    def get_detection_results(
        db: Session,
        filters: DetectionFilterSchema
    ) -> List[DetectionResult]:
        """Get detection results with filters"""
        
        query = db.query(DetectionResult)
        
        # Apply filters
        if filters.model_name:
            query = query.filter(DetectionResult.model_name == filters.model_name)
        
        if filters.start_date:
            query = query.filter(DetectionResult.created_at >= filters.start_date)
        
        if filters.end_date:
            query = query.filter(DetectionResult.created_at <= filters.end_date)
        
        # Filter by class name or confidence (requires joining with detection objects)
        if filters.class_name or filters.min_confidence or filters.max_confidence:
            query = query.join(DetectionObject)
            
            if filters.class_name:
                query = query.filter(DetectionObject.class_name == filters.class_name)
            
            if filters.min_confidence:
                query = query.filter(DetectionObject.confidence >= filters.min_confidence)
            
            if filters.max_confidence:
                query = query.filter(DetectionObject.confidence <= filters.max_confidence)
        
        # Order by most recent first
        query = query.order_by(desc(DetectionResult.created_at))
        
        # Apply pagination
        if filters.offset:
            query = query.offset(filters.offset)
        
        if filters.limit:
            query = query.limit(filters.limit)
        
        return query.all()
    
    @staticmethod
    def get_detection_by_id(db: Session, detection_id: int) -> Optional[DetectionResult]:
        """Get a specific detection result by ID"""
        return db.query(DetectionResult).filter(DetectionResult.id == detection_id).first()
    
    @staticmethod
    def get_detection_objects(db: Session, detection_result_id: int) -> List[DetectionObject]:
        """Get all detection objects for a specific detection result"""
        return db.query(DetectionObject).filter(
            DetectionObject.detection_result_id == detection_result_id
        ).all()
    
    @staticmethod
    def get_detection_stats(db: Session) -> DetectionStatsSchema:
        """Get detection statistics"""
        
        # Total detections
        total_detections = db.query(DetectionResult).count()
        
        # Unique models
        unique_models = db.query(DetectionResult.model_name).distinct().count()
        
        # Most common class
        most_common_class_result = db.query(
            DetectionObject.class_name,
            func.count(DetectionObject.class_name).label('count')
        ).group_by(DetectionObject.class_name).order_by(desc('count')).first()
        
        most_common_class = most_common_class_result[0] if most_common_class_result else None
        
        # Average confidence
        avg_confidence_result = db.query(func.avg(DetectionObject.confidence)).scalar()
        average_confidence = float(avg_confidence_result) if avg_confidence_result else None
        
        # Detections by model
        detections_by_model = {}
        model_stats = db.query(
            DetectionResult.model_name,
            func.count(DetectionResult.id).label('count')
        ).group_by(DetectionResult.model_name).all()
        
        for model_name, count in model_stats:
            detections_by_model[model_name] = count
        
        # Detections by class
        detections_by_class = {}
        class_stats = db.query(
            DetectionObject.class_name,
            func.count(DetectionObject.id).label('count')
        ).group_by(DetectionObject.class_name).all()
        
        for class_name, count in class_stats:
            detections_by_class[class_name] = count
        
        # Recent detections (last 24 hours)
        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_detections = db.query(DetectionResult).filter(
            DetectionResult.created_at >= yesterday
        ).count()
        
        return DetectionStatsSchema(
            total_detections=total_detections,
            unique_models=unique_models,
            most_common_class=most_common_class,
            average_confidence=average_confidence,
            detections_by_model=detections_by_model,
            detections_by_class=detections_by_class,
            recent_detections=recent_detections
        )
    
    @staticmethod
    def delete_detection_result(db: Session, detection_id: int) -> bool:
        """Delete a detection result and its associated objects"""
        
        # Delete associated detection objects first
        db.query(DetectionObject).filter(
            DetectionObject.detection_result_id == detection_id
        ).delete()
        
        # Delete the main detection result
        result = db.query(DetectionResult).filter(DetectionResult.id == detection_id).delete()
        
        db.commit()
        return result > 0
    
    @staticmethod
    def cleanup_old_detections(db: Session, days_to_keep: int = 30) -> int:
        """Clean up old detection results"""
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        # Get IDs of old detection results
        old_detection_ids = db.query(DetectionResult.id).filter(
            DetectionResult.created_at < cutoff_date
        ).all()
        
        if not old_detection_ids:
            return 0
        
        old_ids = [id_tuple[0] for id_tuple in old_detection_ids]
        
        # Delete associated detection objects
        db.query(DetectionObject).filter(
            DetectionObject.detection_result_id.in_(old_ids)
        ).delete(synchronize_session=False)
        
        # Delete old detection results
        deleted_count = db.query(DetectionResult).filter(
            DetectionResult.created_at < cutoff_date
        ).delete(synchronize_session=False)
        
        db.commit()
        return deleted_count