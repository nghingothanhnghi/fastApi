# app/camera_object_detection/models/hardware_detection.py
# Model for tracking hardware detections at specific locations

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class HardwareDetection(Base):
    """
    Tracks hardware components detected by camera at specific locations
    Links camera detections to hydro system device locations
    """
    __tablename__ = "hardware_detections"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Link to original detection result
    detection_result_id = Column(Integer, ForeignKey("detection_results.id"), nullable=False)
    detection_object_id = Column(Integer, ForeignKey("detection_objects.id"), nullable=True)
    
    # Location information (matches HydroDevice.location field)
    location = Column(String, nullable=False, index=True)  # e.g., "Greenhouse A", "Zone 1"
    
    # Hardware information
    hardware_type = Column(String, nullable=False, index=True)  # "pump", "sensor", "relay", "valve", etc.
    hardware_name = Column(String, nullable=True)  # Optional descriptive name
    
    # Detection details
    confidence = Column(Float, nullable=False)
    detected_class = Column(String, nullable=False)  # Original class name from detection
    
    # Bounding box for hardware location in image
    bbox_x1 = Column(Float, nullable=False)
    bbox_y1 = Column(Float, nullable=False)
    bbox_x2 = Column(Float, nullable=False)
    bbox_y2 = Column(Float, nullable=False)
    
    # Status tracking
    is_expected = Column(Boolean, default=True)  # Whether this hardware should be at this location
    is_validated = Column(Boolean, default=False)  # Whether detection has been manually validated
    validation_notes = Column(Text, nullable=True)  # Manual validation notes
    
    # Condition assessment
    condition_status = Column(String, nullable=True)  # "good", "damaged", "missing", "unknown"
    condition_notes = Column(Text, nullable=True)
    
    # Metadata
    camera_source = Column(String, nullable=True)  # Camera identifier if multiple cameras
    detection_metadata = Column(JSON, nullable=True)  # Additional detection info
    
    # Timestamps
    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    validated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<HardwareDetection(id={self.id}, type={self.hardware_type}, location={self.location}, conf={self.confidence:.2f})>"


class LocationHardwareInventory(Base):
    """
    Expected hardware inventory for each location
    Used to validate what should be present vs what's detected
    """
    __tablename__ = "location_hardware_inventory"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Location information
    location = Column(String, nullable=False, index=True)
    
    # Expected hardware
    hardware_type = Column(String, nullable=False)  # "pump", "sensor", "relay", etc.
    hardware_name = Column(String, nullable=True)
    expected_quantity = Column(Integer, default=1)
    
    # Optional linking to actual hydro devices/actuators
    hydro_device_id = Column(Integer, ForeignKey("devices_hydro.id"), nullable=True)
    hydro_actuator_id = Column(Integer, ForeignKey("hydro_actuators.id"), nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<LocationHardwareInventory(id={self.id}, location={self.location}, type={self.hardware_type})>"


class HardwareDetectionSummary(Base):
    """
    Periodic summaries of hardware detection status by location
    Useful for monitoring and reporting
    """
    __tablename__ = "hardware_detection_summaries"
    
    id = Column(Integer, primary_key=True, index=True)
    
    location = Column(String, nullable=False, index=True)
    summary_date = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Detection statistics
    total_detections = Column(Integer, default=0)
    unique_hardware_types = Column(Integer, default=0)
    validated_detections = Column(Integer, default=0)
    
    # Status counts
    expected_present = Column(Integer, default=0)  # Expected hardware that was detected
    expected_missing = Column(Integer, default=0)  # Expected hardware not detected
    unexpected_present = Column(Integer, default=0)  # Hardware detected but not expected
    
    # Condition summary
    good_condition = Column(Integer, default=0)
    damaged_condition = Column(Integer, default=0)
    unknown_condition = Column(Integer, default=0)
    
    # Summary data
    hardware_types_detected = Column(JSON, nullable=True)  # List of detected types
    detection_confidence_avg = Column(Float, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<HardwareDetectionSummary(id={self.id}, location={self.location}, date={self.summary_date})>"