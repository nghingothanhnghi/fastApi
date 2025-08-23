# app/camera_object_detection/services/hardware_detection_service.py
# Service for managing hardware detection and location-based validation

from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, or_
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

from app.camera_object_detection.models.detection import DetectionResult, DetectionObject
from app.camera_object_detection.models.hardware_detection import HardwareDetection, LocationHardwareInventory, HardwareDetectionSummary
from app.camera_object_detection.schemas.hardware_detection import (
    HardwareDetectionCreate, HardwareDetectionUpdate, HardwareDetectionFilter,
    LocationHardwareInventoryCreate, LocationHardwareInventoryUpdate,
    LocationStatusResponse, HardwareDetectionStats, BulkHardwareDetectionCreate,
    HardwareValidationRequest, HardwareDetectionSummaryResponse
)
from app.hydro_system.models.device import HydroDevice
from app.hydro_system.models.actuator import HydroActuator

from app.core.logging_config import get_logger

logger = get_logger(__name__)


class HardwareDetectionService:
    
    # Hardware type mapping from detection classes to hydro system types
    HARDWARE_TYPE_MAPPING = {
        # Detection class -> Hardware type
        "pump": "pump",
        "water_pump": "water_pump", 
        "motor": "pump",
        "light": "light",
        "led": "light",
        "grow_light": "light",
        "fan": "fan",
        "exhaust_fan": "fan",
        "valve": "valve",
        "solenoid": "valve",
        "sensor": "sensor",
        "temperature_sensor": "sensor",
        "humidity_sensor": "sensor",
        "ph_sensor": "sensor",
        "relay": "relay",
        "controller": "controller",
        "esp32": "controller",
        "arduino": "controller",
        "tank": "tank",
        "reservoir": "tank",
        "pipe": "pipe",
        "tube": "pipe",
        "cable": "cable",
        "wire": "cable",
    }
    @staticmethod
    def get_camera_sources_by_location(db: Session, location: str) -> List[str]:
        sources = (
            db.query(HardwareDetection.camera_source)
            .filter(HardwareDetection.location == location)
            .filter(HardwareDetection.camera_source.isnot(None))
            .distinct()
            .all()
        )
        return [source[0] for source in sources]
    
    @staticmethod
    def create_hardware_detection(
        db: Session,
        detection_data: HardwareDetectionCreate
    ) -> HardwareDetection:
        """Create a new hardware detection record"""
        
        # Map detected class to hardware type if not explicitly provided
        if detection_data.hardware_type == "other" or not detection_data.hardware_type:
            mapped_type = HardwareDetectionService.HARDWARE_TYPE_MAPPING.get(
                detection_data.detected_class.lower(), "other"
            )
            detection_data.hardware_type = mapped_type
        
        hardware_detection = HardwareDetection(**detection_data.dict())
        db.add(hardware_detection)
        db.commit()
        db.refresh(hardware_detection)
        
        logger.info(f"Created hardware detection: {hardware_detection.hardware_type} at {hardware_detection.location}")
        return hardware_detection
    
    @staticmethod
    def create_bulk_hardware_detections(
        db: Session,
        bulk_data: BulkHardwareDetectionCreate
    ) -> List[HardwareDetection]:
        """Create multiple hardware detections from a single detection result"""
        
        created_detections = []
        
        for detection_data in bulk_data.detections:
            # Set common fields
            detection_data.location = bulk_data.location
            if bulk_data.camera_source:
                detection_data.camera_source = bulk_data.camera_source
            
            detection = HardwareDetectionService.create_hardware_detection(db, detection_data)
            created_detections.append(detection)
        
        logger.info(f"Created {len(created_detections)} hardware detections for location {bulk_data.location}")
        return created_detections
    
    @staticmethod
    def process_detection_result_for_hardware(
        db: Session,
        detection_result_id: int,
        location: str,
        camera_source: Optional[str] = None,
        confidence_threshold: float = 0.5
    ) -> List[HardwareDetection]:
        """
        Process a detection result and create hardware detection records
        for any detected hardware components
        """
        
        # Get detection objects from the result
        detection_objects = db.query(DetectionObject).filter(
            DetectionObject.detection_result_id == detection_result_id,
            DetectionObject.confidence >= confidence_threshold
        ).all()
        
        hardware_detections = []
        
        for obj in detection_objects:
            # Check if this class maps to a hardware type
            hardware_type = HardwareDetectionService.HARDWARE_TYPE_MAPPING.get(
                obj.class_name.lower(), None
            )
            
            if hardware_type:
                detection_data = HardwareDetectionCreate(
                    detection_result_id=detection_result_id,
                    detection_object_id=obj.id,
                    location=location,
                    hardware_type=hardware_type,
                    confidence=obj.confidence,
                    detected_class=obj.class_name,
                    bbox_x1=obj.bbox_x1,
                    bbox_y1=obj.bbox_y1,
                    bbox_x2=obj.bbox_x2,
                    bbox_y2=obj.bbox_y2,
                    camera_source=camera_source
                )
                
                hardware_detection = HardwareDetectionService.create_hardware_detection(
                    db, detection_data
                )
                hardware_detections.append(hardware_detection)
        
        logger.info(f"Processed detection result {detection_result_id}: found {len(hardware_detections)} hardware items")
        return hardware_detections
    
    @staticmethod
    def get_hardware_detections(
        db: Session,
        filters: HardwareDetectionFilter
    ) -> List[HardwareDetection]:
        """Get hardware detections with filters"""
        
        query = db.query(HardwareDetection)
        
        # Apply filters
        if filters.location:
            query = query.filter(HardwareDetection.location == filters.location)
        
        if filters.hardware_type:
            query = query.filter(HardwareDetection.hardware_type == filters.hardware_type)
        
        if filters.condition_status:
            query = query.filter(HardwareDetection.condition_status == filters.condition_status)
        
        if filters.is_validated is not None:
            query = query.filter(HardwareDetection.is_validated == filters.is_validated)
        
        if filters.is_expected is not None:
            query = query.filter(HardwareDetection.is_expected == filters.is_expected)
        
        if filters.min_confidence:
            query = query.filter(HardwareDetection.confidence >= filters.min_confidence)
        
        if filters.start_date:
            query = query.filter(HardwareDetection.detected_at >= filters.start_date)
        
        if filters.end_date:
            query = query.filter(HardwareDetection.detected_at <= filters.end_date)
        
        if filters.camera_source:
            query = query.filter(HardwareDetection.camera_source == filters.camera_source)
        
        # Order by most recent first
        query = query.order_by(desc(HardwareDetection.detected_at))
        
        # Apply pagination
        if filters.offset:
            query = query.offset(filters.offset)
        
        if filters.limit:
            query = query.limit(filters.limit)
        
        return query.all()
    
    @staticmethod
    def validate_hardware_detection(
        db: Session,
        detection_id: int,
        validation_data: HardwareValidationRequest
    ) -> HardwareDetection:
        """Validate a hardware detection"""
        
        detection = db.query(HardwareDetection).filter(
            HardwareDetection.id == detection_id
        ).first()
        
        if not detection:
            raise ValueError(f"Hardware detection {detection_id} not found")
        
        # Update validation fields
        detection.is_validated = validation_data.is_validated
        detection.validation_notes = validation_data.validation_notes
        detection.validated_at = datetime.utcnow()
        
        if validation_data.condition_status:
            detection.condition_status = validation_data.condition_status
        
        if validation_data.condition_notes:
            detection.condition_notes = validation_data.condition_notes
        
        db.commit()
        db.refresh(detection)
        
        logger.info(f"Validated hardware detection {detection_id}: {validation_data.is_validated}")
        return detection
    
    @staticmethod
    def get_location_status(
        db: Session,
        location: str
    ) -> LocationStatusResponse:
        """Get comprehensive status for a location"""
        
        # Get expected hardware for this location
        expected_inventory = db.query(LocationHardwareInventory).filter(
            LocationHardwareInventory.location == location,
            LocationHardwareInventory.is_active == True
        ).all()
        
        # Get recent detections for this location (last 24 hours)
        recent_cutoff = datetime.utcnow() - timedelta(hours=24)
        recent_detections = db.query(HardwareDetection).filter(
            HardwareDetection.location == location,
            HardwareDetection.detected_at >= recent_cutoff
        ).all()
        
        # Calculate statistics
        total_expected = sum(item.expected_quantity for item in expected_inventory)
        total_detected = len(recent_detections)
        validated_count = len([d for d in recent_detections if d.is_validated])
        
        # Find missing and unexpected hardware
        expected_types = {item.hardware_type for item in expected_inventory}
        detected_types = {d.hardware_type for d in recent_detections}
        
        missing_hardware = list(expected_types - detected_types)
        unexpected_hardware = list(detected_types - expected_types)
        
        # Hardware status summary
        hardware_status = {}
        for hw_type in expected_types.union(detected_types):
            detections = [d for d in recent_detections if d.hardware_type == hw_type]
            expected_count = sum(
                item.expected_quantity for item in expected_inventory 
                if item.hardware_type == hw_type
            )
            
            hardware_status[hw_type] = {
                "expected_count": expected_count,
                "detected_count": len(detections),
                "validated_count": len([d for d in detections if d.is_validated]),
                "avg_confidence": sum(d.confidence for d in detections) / len(detections) if detections else 0,
                "conditions": {
                    "good": len([d for d in detections if d.condition_status == "good"]),
                    "damaged": len([d for d in detections if d.condition_status == "damaged"]),
                    "unknown": len([d for d in detections if d.condition_status == "unknown"]),
                }
            }
        
        # Last detection time
        last_detection = max(
            (d.detected_at for d in recent_detections), 
            default=None
        )
        
        # Average confidence
        avg_confidence = (
            sum(d.confidence for d in recent_detections) / len(recent_detections)
            if recent_detections else None
        )
        
        return LocationStatusResponse(
            location=location,
            total_expected=total_expected,
            total_detected=total_detected,
            validated_count=validated_count,
            missing_hardware=missing_hardware,
            unexpected_hardware=unexpected_hardware,
            hardware_status=hardware_status,
            last_detection=last_detection,
            detection_confidence_avg=avg_confidence
        )
    
    @staticmethod
    def create_location_inventory(
        db: Session,
        inventory_data: LocationHardwareInventoryCreate
    ) -> LocationHardwareInventory:
        """Create expected hardware inventory for a location"""
        
        inventory = LocationHardwareInventory(**inventory_data.dict())
        db.add(inventory)
        db.commit()
        db.refresh(inventory)
        
        logger.info(f"Created inventory item: {inventory.hardware_type} at {inventory.location}")
        return inventory
    
    @staticmethod
    def sync_location_inventory_with_hydro_devices(
        db: Session,
        location: str
    ) -> List[LocationHardwareInventory]:
        """
        Idempotent sync: ensure inventory entries exist for hydro devices/actuators
        at the specified location without creating duplicates.
        Matching rules:
        - Device entry: match by (location, hydro_device_id, hardware_type='controller')
        - Actuator entry: match by (location, hydro_actuator_id)
        Updates:
        - If exists, ensure is_active=True and update name/notes if changed.
        - If not exists, create a new inventory entry.
        """
        
        # Get hydro devices at this location
        hydro_devices = db.query(HydroDevice).filter(
            HydroDevice.location == location,
            HydroDevice.is_active == True
        ).all()
        
        synced_inventory: List[LocationHardwareInventory] = []
        
        for device in hydro_devices:
            # Upsert inventory item for the device itself (controller)
            existing_device_item = db.query(LocationHardwareInventory).filter(
                LocationHardwareInventory.location == location,
                LocationHardwareInventory.hydro_device_id == device.id,
                LocationHardwareInventory.hardware_type == "controller",
            ).first()
            device_name = f"{device.name} Controller"
            device_notes = f"Auto-synced from hydro device: {device.device_id}"

            if existing_device_item:
                # Update minimal fields if needed
                updated = False
                if existing_device_item.hardware_name != device_name:
                    existing_device_item.hardware_name = device_name
                    updated = True
                if existing_device_item.notes != device_notes:
                    existing_device_item.notes = device_notes
                    updated = True
                if existing_device_item.is_active is False:
                    existing_device_item.is_active = True
                    updated = True
                if updated:
                    db.commit()
                    db.refresh(existing_device_item)
                synced_inventory.append(existing_device_item)
            else:
                device_inventory = LocationHardwareInventoryCreate(
                    location=location,
                    hardware_type="controller",
                    hardware_name=device_name,
                    expected_quantity=1,
                    hydro_device_id=device.id,
                    notes=device_notes,
                )
                inventory_item = HardwareDetectionService.create_location_inventory(db, device_inventory)
                synced_inventory.append(inventory_item)
            
            # Upsert inventory items for each actuator
            for actuator in getattr(device, "actuators", []):
                if not actuator.is_active:
                    continue
                existing_act_item = db.query(LocationHardwareInventory).filter(
                    LocationHardwareInventory.location == location,
                    LocationHardwareInventory.hydro_actuator_id == actuator.id,
                ).first()
                act_name = actuator.name or f"{actuator.type.title()} {actuator.port}"
                act_notes = f"Auto-synced from actuator: {actuator.type} on pin {actuator.pin}"

                if existing_act_item:
                    updated = False
                    if existing_act_item.hardware_type != actuator.type:
                        existing_act_item.hardware_type = actuator.type
                        updated = True
                    if existing_act_item.hardware_name != act_name:
                        existing_act_item.hardware_name = act_name
                        updated = True
                    if existing_act_item.notes != act_notes:
                        existing_act_item.notes = act_notes
                        updated = True
                    if existing_act_item.is_active is False:
                        existing_act_item.is_active = True
                        updated = True
                    if existing_act_item.expected_quantity != 1:
                        existing_act_item.expected_quantity = 1
                        updated = True
                    if updated:
                        db.commit()
                        db.refresh(existing_act_item)
                    synced_inventory.append(existing_act_item)
                else:
                    actuator_inventory = LocationHardwareInventoryCreate(
                        location=location,
                        hardware_type=actuator.type,
                        hardware_name=act_name,
                        expected_quantity=1,
                        hydro_device_id=device.id,
                        hydro_actuator_id=actuator.id,
                        notes=act_notes,
                    )
                    inventory_item = HardwareDetectionService.create_location_inventory(db, actuator_inventory)
                    synced_inventory.append(inventory_item)
        
        logger.info(f"Synced {len(synced_inventory)} inventory items for location {location}")
        return synced_inventory
    
    @staticmethod
    def get_hardware_detection_stats(db: Session) -> HardwareDetectionStats:
        """Get overall hardware detection statistics"""
        
        # Basic counts
        total_locations = db.query(HardwareDetection.location).distinct().count()
        total_detections = db.query(HardwareDetection).count()
        total_validated = db.query(HardwareDetection).filter(
            HardwareDetection.is_validated == True
        ).count()
        
        # Hardware types count
        hardware_types_result = db.query(
            HardwareDetection.hardware_type,
            func.count(HardwareDetection.id).label('count')
        ).group_by(HardwareDetection.hardware_type).all()
        
        hardware_types_count = {hw_type: count for hw_type, count in hardware_types_result}
        
        # Condition status count
        condition_status_result = db.query(
            HardwareDetection.condition_status,
            func.count(HardwareDetection.id).label('count')
        ).filter(HardwareDetection.condition_status.isnot(None)).group_by(
            HardwareDetection.condition_status
        ).all()
        
        condition_status_count = {status: count for status, count in condition_status_result}
        
        # Locations with issues
        locations_with_missing = []
        locations_with_unexpected = []
        
        # This would require more complex queries to determine missing/unexpected
        # For now, we'll leave these as empty lists and implement later if needed
        
        # Average confidence
        avg_confidence_result = db.query(func.avg(HardwareDetection.confidence)).scalar()
        average_confidence = float(avg_confidence_result) if avg_confidence_result else None
        
        return HardwareDetectionStats(
            total_locations=total_locations,
            total_detections=total_detections,
            total_validated=total_validated,
            hardware_types_count=hardware_types_count,
            condition_status_count=condition_status_count,
            locations_with_missing_hardware=locations_with_missing,
            locations_with_unexpected_hardware=locations_with_unexpected,
            average_confidence=average_confidence,
            detection_trend={}  # Implement trend analysis later if needed
        )
    
    def get_hardware_detection_summaries(
        self, 
        db: Session, 
        location: Optional[str] = None
    ) -> List[HardwareDetectionSummaryResponse]:
        """Get hardware detection summaries, optionally filtered by location"""
        try:
            query = db.query(HardwareDetectionSummary)
            
            if location:
                query = query.filter(HardwareDetectionSummary.location == location)
            
            # Order by most recent first
            summaries = query.order_by(desc(HardwareDetectionSummary.summary_date)).all()
            
            # If no summaries exist, generate them from current detection data
            if not summaries:
                logger.info(f"No summaries found, generating from current data for location: {location}")
                summaries = self._generate_summaries_from_detections(db, location)
            
            return summaries
            
        except Exception as e:
            logger.error(f"Error getting hardware detection summaries: {e}")
            raise
    
    def _generate_summaries_from_detections(
        self, 
        db: Session, 
        location: Optional[str] = None
    ) -> List[HardwareDetectionSummary]:
        """Generate summary data from existing detections when no summaries exist"""
        try:
            # Get locations to summarize
            if location:
                locations = [location]
            else:
                locations_result = db.query(HardwareDetection.location).distinct().all()
                locations = [loc[0] for loc in locations_result]
            
            summaries = []
            current_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            
            for loc in locations:
                # Get detections for this location from the last 24 hours
                cutoff_date = current_date - timedelta(days=1)
                detections = db.query(HardwareDetection).filter(
                    HardwareDetection.location == loc,
                    HardwareDetection.detected_at >= cutoff_date
                ).all()
                
                if not detections:
                    continue
                
                # Calculate summary statistics
                total_detections = len(detections)
                unique_hardware_types = len(set(d.hardware_type for d in detections))
                validated_detections = len([d for d in detections if d.is_validated])
                expected_present = len([d for d in detections if d.is_expected])
                expected_missing = 0  # Would need inventory comparison
                unexpected_present = len([d for d in detections if not d.is_expected])
                
                # Condition counts
                good_condition = len([d for d in detections if d.condition_status == "good"])
                damaged_condition = len([d for d in detections if d.condition_status == "damaged"])
                unknown_condition = len([d for d in detections if d.condition_status in ["unknown", None]])
                
                # Hardware types detected
                hardware_types_detected = list(set(d.hardware_type for d in detections))
                
                # Average confidence
                confidences = [d.confidence for d in detections if d.confidence is not None]
                detection_confidence_avg = sum(confidences) / len(confidences) if confidences else None
                
                # Create summary record
                summary = HardwareDetectionSummary(
                    location=loc,
                    summary_date=current_date,
                    total_detections=total_detections,
                    unique_hardware_types=unique_hardware_types,
                    validated_detections=validated_detections,
                    expected_present=expected_present,
                    expected_missing=expected_missing,
                    unexpected_present=unexpected_present,
                    good_condition=good_condition,
                    damaged_condition=damaged_condition,
                    unknown_condition=unknown_condition,
                    hardware_types_detected=hardware_types_detected,
                    detection_confidence_avg=detection_confidence_avg
                )
                
                # Save to database
                db.add(summary)
                summaries.append(summary)
            
            db.commit()
            logger.info(f"Generated {len(summaries)} summaries from detection data")
            return summaries
            
        except Exception as e:
            logger.error(f"Error generating summaries from detections: {e}")
            db.rollback()
            raise
    
    @staticmethod
    def enhance_detections_with_hardware_info(
        detections: List[Dict[str, Any]], 
        known_actuators: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Enhance detection results with known hardware information"""
        
        enhanced_detections = []
        
        for detection in detections:
            enhanced_detection = detection.copy()
            
            # Check if this detection matches any known hardware type
            original_class = detection.get("original_class", detection.get("class_name", ""))
            mapped_hardware = HardwareDetectionService.HARDWARE_TYPE_MAPPING.get(original_class.lower())
            
            if mapped_hardware:
                enhanced_detection["hardware_type"] = mapped_hardware
                enhanced_detection["is_hardware"] = True
                
                # Try to match with known actuators
                matching_actuators = [
                    actuator for actuator in known_actuators 
                    if actuator["type"].lower() in mapped_hardware.lower() or 
                       mapped_hardware.lower() in actuator["type"].lower()
                ]
                
                if matching_actuators:
                    enhanced_detection["matching_actuators"] = matching_actuators
                    enhanced_detection["actuator_count"] = len(matching_actuators)
            else:
                enhanced_detection["is_hardware"] = False
                enhanced_detection["hardware_type"] = None
            
            enhanced_detections.append(enhanced_detection)
        
        return enhanced_detections
    
    @staticmethod
    def get_hardware_statistics(detections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate statistics about detected hardware"""
        hardware_detections = [d for d in detections if d.get("is_hardware", False)]
        
        if not hardware_detections:
            return {
                "total_hardware": 0,
                "hardware_types": {},
                "average_confidence": 0,
                "known_actuators_detected": 0,
                "unique_hardware_types": 0
            }
        
        hardware_types = {}
        total_confidence = 0
        known_actuators = 0
        
        for detection in hardware_detections:
            hardware_type = detection.get("hardware_type", "unknown")
            hardware_types[hardware_type] = hardware_types.get(hardware_type, 0) + 1
            total_confidence += detection.get("confidence", 0)
            
            if detection.get("matching_actuators"):
                known_actuators += len(detection["matching_actuators"])
        
        return {
            "total_hardware": len(hardware_detections),
            "hardware_types": hardware_types,
            "average_confidence": total_confidence / len(hardware_detections),
            "known_actuators_detected": known_actuators,
            "unique_hardware_types": len(hardware_types)
        }


# Export service instance
hardware_detection_service = HardwareDetectionService()