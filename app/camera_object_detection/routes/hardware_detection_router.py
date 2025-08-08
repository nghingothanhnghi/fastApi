# app/camera_object_detection/routes/hardware_detection_router.py
# API routes for hardware detection and location-based validation

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import asyncio

from app.database import get_db
from app.camera_object_detection.services.hardware_detection_service import hardware_detection_service
from app.camera_object_detection.schemas.hardware_detection import (
    HardwareDetectionCreate, HardwareDetectionUpdate, HardwareDetectionResponse,
    HardwareDetectionFilter, LocationStatusResponse, HardwareDetectionStats,
    BulkHardwareDetectionCreate, HardwareValidationRequest,
    LocationHardwareInventoryCreate, LocationHardwareInventoryResponse,
    LocationHardwareInventoryUpdate, ConditionStatus, HardwareType
)
from app.camera_object_detection.websocket.events import (
    broadcast_new_detection, broadcast_detection_validated, broadcast_bulk_detections,
    broadcast_detection_processed, broadcast_location_status_change, 
    broadcast_inventory_updated, broadcast_hydro_device_matched, broadcast_stats_updated
)

router = APIRouter(prefix="/hardware-detection", tags=["Hardware Detection"])


# Hardware Detection Endpoints
@router.post("/", response_model=HardwareDetectionResponse)
async def create_hardware_detection(
    detection_data: HardwareDetectionCreate,
    db: Session = Depends(get_db)
):
    """Create a new hardware detection record"""
    try:
        detection = hardware_detection_service.create_hardware_detection(db, detection_data)
        
        # Broadcast new detection event
        detection_dict = detection.dict() if hasattr(detection, 'dict') else detection.__dict__
        asyncio.create_task(broadcast_new_detection(detection_dict, detection_data.location))
        
        return detection
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bulk", response_model=List[HardwareDetectionResponse])
async def create_bulk_hardware_detections(
    bulk_data: BulkHardwareDetectionCreate,
    db: Session = Depends(get_db)
):
    """Create multiple hardware detections from a single detection result"""
    try:
        detections = hardware_detection_service.create_bulk_hardware_detections(db, bulk_data)
        
        # Broadcast bulk detections event
        detections_dict = [d.dict() if hasattr(d, 'dict') else d.__dict__ for d in detections]
        asyncio.create_task(broadcast_bulk_detections(detections_dict, bulk_data.location, len(detections)))
        
        return detections
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/process-detection/{detection_result_id}", response_model=List[HardwareDetectionResponse])
async def process_detection_for_hardware(
    detection_result_id: int = Path(..., description="Detection result ID to process"),
    location: str = Query(..., description="Location where detection was made"),
    camera_source: Optional[str] = Query(None, description="Camera source identifier"),
    confidence_threshold: float = Query(0.5, ge=0.0, le=1.0, description="Minimum confidence threshold"),
    db: Session = Depends(get_db)
):
    """Process a detection result and create hardware detection records"""
    try:
        detections = hardware_detection_service.process_detection_result_for_hardware(
            db, detection_result_id, location, camera_source, confidence_threshold
        )
        
        # Broadcast detection processed event
        detections_dict = [d.dict() if hasattr(d, 'dict') else d.__dict__ for d in detections]
        asyncio.create_task(broadcast_detection_processed(detections_dict, location, detection_result_id))
        
        return detections
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/", response_model=List[HardwareDetectionResponse])
async def get_hardware_detections(
    location: Optional[str] = Query(None, description="Filter by location"),
    hardware_type: Optional[str] = Query(None, description="Filter by hardware type"),
    condition_status: Optional[ConditionStatus] = Query(None, description="Filter by condition status"),
    is_validated: Optional[bool] = Query(None, description="Filter by validation status"),
    is_expected: Optional[bool] = Query(None, description="Filter by expected status"),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0, description="Minimum confidence"),
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter"),
    camera_source: Optional[str] = Query(None, description="Filter by camera source"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: Session = Depends(get_db)
):
    """Get hardware detections with filters"""
    filters = HardwareDetectionFilter(
        location=location,
        hardware_type=hardware_type,
        condition_status=condition_status,
        is_validated=is_validated,
        is_expected=is_expected,
        min_confidence=min_confidence,
        start_date=start_date,
        end_date=end_date,
        camera_source=camera_source,
        limit=limit,
        offset=offset
    )
    
    detections = hardware_detection_service.get_hardware_detections(db, filters)
    return detections


@router.put("/{detection_id}/validate", response_model=HardwareDetectionResponse)
async def validate_hardware_detection(
    detection_id: int = Path(..., description="Hardware detection ID"),
    validation_data: HardwareValidationRequest = ...,
    db: Session = Depends(get_db)
):
    """Validate a hardware detection"""
    try:
        detection = hardware_detection_service.validate_hardware_detection(
            db, detection_id, validation_data
        )
        
        # Broadcast validation event
        detection_dict = detection.dict() if hasattr(detection, 'dict') else detection.__dict__
        location = detection_dict.get('location', 'unknown')
        validation_status = validation_data.is_valid
        asyncio.create_task(broadcast_detection_validated(detection_dict, location, validation_status))
        
        return detection
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Location Status Endpoints
@router.get("/location/{location}/status", response_model=LocationStatusResponse)
async def get_location_status(
    location: str = Path(..., description="Location identifier"),
    db: Session = Depends(get_db)
):
    """Get comprehensive hardware status for a location"""
    try:
        status = hardware_detection_service.get_location_status(db, location)
        return status
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Location Inventory Endpoints
@router.post("/inventory", response_model=LocationHardwareInventoryResponse)
async def create_location_inventory(
    inventory_data: LocationHardwareInventoryCreate,
    db: Session = Depends(get_db)
):
    """Create expected hardware inventory for a location"""
    try:
        inventory = hardware_detection_service.create_location_inventory(db, inventory_data)
        
        # Broadcast inventory update
        inventory_dict = inventory.dict() if hasattr(inventory, 'dict') else inventory.__dict__
        asyncio.create_task(broadcast_inventory_updated(inventory_data.location, inventory_dict))
        
        return inventory
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/inventory/sync/{location}", response_model=List[LocationHardwareInventoryResponse])
async def sync_location_inventory(
    location: str = Path(..., description="Location to sync inventory for"),
    db: Session = Depends(get_db)
):
    """Automatically sync inventory with hydro devices at location"""
    try:
        inventory_items = hardware_detection_service.sync_location_inventory_with_hydro_devices(
            db, location
        )
        
        # Broadcast inventory sync update
        inventory_dict = [item.dict() if hasattr(item, 'dict') else item.__dict__ for item in inventory_items]
        asyncio.create_task(broadcast_inventory_updated(location, {
            "synced_items": inventory_dict,
            "count": len(inventory_items),
            "sync_type": "hydro_devices"
        }))
        
        return inventory_items
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Statistics and Reporting
@router.get("/stats", response_model=HardwareDetectionStats)
async def get_hardware_detection_stats(db: Session = Depends(get_db)):
    """Get overall hardware detection statistics"""
    try:
        stats = hardware_detection_service.get_hardware_detection_stats(db)
        
        # Optionally broadcast stats update (uncomment if needed)
        # stats_dict = stats.dict() if hasattr(stats, 'dict') else stats.__dict__
        # asyncio.create_task(broadcast_stats_updated(stats_dict))
        
        return stats
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Utility Endpoints
@router.get("/hardware-types", response_model=List[str])
async def get_supported_hardware_types():
    """Get list of supported hardware types"""
    return [hw_type.value for hw_type in HardwareType]


@router.get("/condition-statuses", response_model=List[str])
async def get_condition_statuses():
    """Get list of possible condition statuses"""
    return [status.value for status in ConditionStatus]


@router.get("/locations", response_model=List[str])
async def get_locations_with_detections(db: Session = Depends(get_db)):
    """Get list of locations that have hardware detections"""
    from ..models.hardware_detection import HardwareDetection
    
    locations = db.query(HardwareDetection.location).distinct().all()
    return [location[0] for location in locations]


@router.get("/hardware-mapping")
async def get_hardware_type_mapping():
    """Get the mapping from detection classes to hardware types"""
    return hardware_detection_service.HARDWARE_TYPE_MAPPING


# Hydro System Integration Endpoints
@router.get("/hydro-integration/locations", response_model=List[str])
async def get_hydro_locations(db: Session = Depends(get_db)):
    """Get all locations from hydro system"""
    from ..utils.hydro_integration import hydro_integration
    return hydro_integration.get_hydro_locations(db)


@router.get("/hydro-integration/location/{location}/health")
async def get_location_health_report(
    location: str = Path(..., description="Location identifier"),
    db: Session = Depends(get_db)
):
    """Get comprehensive health report for a location"""
    from ..utils.hydro_integration import hydro_integration
    try:
        report = hydro_integration.get_location_health_report(db, location)
        return report
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/hydro-integration/location/{location}/validate")
async def validate_location_hardware(
    location: str = Path(..., description="Location identifier"),
    hours_back: int = Query(24, ge=1, le=168, description="Hours to look back for detections"),
    db: Session = Depends(get_db)
):
    """Validate detected hardware against expected hardware from hydro system"""
    from ..utils.hydro_integration import hydro_integration
    from datetime import datetime, timedelta
    
    try:
        # Get recent detections
        cutoff = datetime.utcnow() - timedelta(hours=hours_back)
        recent_detections = db.query(hardware_detection_service.HardwareDetection).filter(
            hardware_detection_service.HardwareDetection.location == location,
            hardware_detection_service.HardwareDetection.detected_at >= cutoff
        ).all()
        
        validation_report = hydro_integration.validate_detection_against_hydro_system(
            db, location, recent_detections
        )
        return validation_report
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/hydro-integration/camera-placement-suggestions")
async def get_camera_placement_suggestions(db: Session = Depends(get_db)):
    """Get suggestions for optimal camera placement based on hydro device locations"""
    from ..utils.hydro_integration import hydro_integration
    try:
        suggestions = hydro_integration.suggest_camera_placement(db)
        return suggestions
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/hydro-integration/location/{location}/setup-inventory")
async def setup_location_inventory(
    location: str = Path(..., description="Location identifier"),
    db: Session = Depends(get_db)
):
    """Automatically set up hardware inventory for a location based on hydro devices"""
    from ..utils.hydro_integration import hydro_integration
    try:
        inventory_items = hydro_integration.auto_setup_location_inventory(db, location)
        return {
            "location": location,
            "inventory_items_created": len(inventory_items),
            "items": inventory_items
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    

@router.get("/location/{location}/camera-sources", response_model=List[str])
def get_camera_sources_by_location(
    location: str,
    db: Session = Depends(get_db),
):
    """
    Get distinct camera sources for a given location.
    """
    return hardware_detection_service.get_camera_sources_by_location(db, location)
