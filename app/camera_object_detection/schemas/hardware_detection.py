# app/camera_object_detection/schemas/hardware_detection.py
# Pydantic schemas for hardware detection system

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ConditionStatus(str, Enum):
    GOOD = "good"
    DAMAGED = "damaged"
    MISSING = "missing"
    UNKNOWN = "unknown"


class HardwareType(str, Enum):
    PUMP = "pump"
    WATER_PUMP = "water_pump"
    LIGHT = "light"
    FAN = "fan"
    VALVE = "valve"
    SENSOR = "sensor"
    RELAY = "relay"
    CONTROLLER = "controller"
    TANK = "tank"
    PIPE = "pipe"
    CABLE = "cable"
    OTHER = "other"


# Hardware Detection Schemas
class HardwareDetectionBase(BaseModel):
    location: str = Field(..., description="Location where hardware was detected")
    hardware_type: str = Field(..., description="Type of hardware detected")
    hardware_name: Optional[str] = Field(None, description="Optional descriptive name")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence")
    detected_class: str = Field(..., description="Original class name from detection model")
    is_expected: bool = Field(True, description="Whether this hardware should be at this location")
    condition_status: Optional[ConditionStatus] = Field(None, description="Condition assessment")
    condition_notes: Optional[str] = Field(None, description="Notes about hardware condition")
    camera_source: Optional[str] = Field(None, description="Camera identifier")


class HardwareDetectionCreate(HardwareDetectionBase):
    detection_result_id: int = Field(..., description="ID of the detection result")
    detection_object_id: Optional[int] = Field(None, description="ID of the specific detection object")
    bbox_x1: float = Field(..., description="Bounding box x1 coordinate")
    bbox_y1: float = Field(..., description="Bounding box y1 coordinate")
    bbox_x2: float = Field(..., description="Bounding box x2 coordinate")
    bbox_y2: float = Field(..., description="Bounding box y2 coordinate")
    detection_metadata: Optional[Dict[str, Any]] = Field(None, description="Additional detection metadata")


class HardwareDetectionUpdate(BaseModel):
    hardware_name: Optional[str] = None
    is_expected: Optional[bool] = None
    is_validated: Optional[bool] = None
    validation_notes: Optional[str] = None
    condition_status: Optional[ConditionStatus] = None
    condition_notes: Optional[str] = None
    # Allow updating classification fields
    hardware_type: Optional[str] = None
    detected_class: Optional[str] = None


class HardwareDetectionResponse(HardwareDetectionBase):
    id: int
    detection_result_id: int
    detection_object_id: Optional[int]
    bbox_x1: float
    bbox_y1: float
    bbox_x2: float
    bbox_y2: float
    is_validated: bool
    validation_notes: Optional[str]
    detection_metadata: Optional[Dict[str, Any]]
    detected_at: datetime
    validated_at: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# Location Hardware Inventory Schemas
class LocationHardwareInventoryBase(BaseModel):
    location: str = Field(..., description="Location identifier")
    hardware_type: str = Field(..., description="Expected hardware type")
    hardware_name: Optional[str] = Field(None, description="Hardware name/description")
    expected_quantity: int = Field(1, ge=1, description="Expected quantity of this hardware")
    notes: Optional[str] = Field(None, description="Additional notes")


class LocationHardwareInventoryCreate(LocationHardwareInventoryBase):
    hydro_device_id: Optional[int] = Field(None, description="Link to hydro device")
    hydro_actuator_id: Optional[int] = Field(None, description="Link to hydro actuator")


class LocationHardwareInventoryUpdate(BaseModel):
    hardware_name: Optional[str] = None
    expected_quantity: Optional[int] = Field(None, ge=1)
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class LocationHardwareInventoryResponse(LocationHardwareInventoryBase):
    id: int
    hydro_device_id: Optional[int]
    hydro_actuator_id: Optional[int]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# Hardware Detection Summary Schemas
class HardwareDetectionSummaryResponse(BaseModel):
    id: int
    location: str
    summary_date: datetime
    total_detections: int
    unique_hardware_types: int
    validated_detections: int
    expected_present: int
    expected_missing: int
    unexpected_present: int
    good_condition: int
    damaged_condition: int
    unknown_condition: int
    hardware_types_detected: Optional[List[str]]
    detection_confidence_avg: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


# Filter and Query Schemas
class HardwareDetectionFilter(BaseModel):
    location: Optional[str] = None
    hardware_type: Optional[str] = None
    condition_status: Optional[ConditionStatus] = None
    is_validated: Optional[bool] = None
    is_expected: Optional[bool] = None
    min_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    camera_source: Optional[str] = None
    limit: Optional[int] = Field(100, ge=1, le=1000)
    offset: Optional[int] = Field(0, ge=0)


class LocationStatusResponse(BaseModel):
    location: str
    total_expected: int
    total_detected: int
    validated_count: int
    missing_hardware: List[str]
    unexpected_hardware: List[str]
    hardware_status: Dict[str, Dict[str, Any]]  # hardware_type -> {count, condition, etc.}
    last_detection: Optional[datetime]
    detection_confidence_avg: Optional[float]


class HardwareValidationRequest(BaseModel):
    is_validated: bool = Field(..., description="Whether detection is validated")
    validation_notes: Optional[str] = Field(None, description="Validation notes")
    condition_status: Optional[ConditionStatus] = Field(None, description="Hardware condition")
    condition_notes: Optional[str] = Field(None, description="Condition notes")


# Bulk operations
class BulkHardwareDetectionCreate(BaseModel):
    detections: List[HardwareDetectionCreate] = Field(..., description="List of hardware detections to create")
    location: str = Field(..., description="Location for all detections")
    camera_source: Optional[str] = Field(None, description="Camera source for all detections")


class HardwareDetectionStats(BaseModel):
    total_locations: int
    total_detections: int
    total_validated: int
    hardware_types_count: Dict[str, int]
    condition_status_count: Dict[str, int]
    locations_with_missing_hardware: List[str]
    locations_with_unexpected_hardware: List[str]
    average_confidence: Optional[float]
    detection_trend: Optional[Dict[str, int]]  # date -> count for last 7 days