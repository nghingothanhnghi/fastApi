# Camera Object Detection + Hydro System Integration

This document explains how to use camera object detection to monitor and validate hardware components in your hydroponic system based on device locations.

## Overview

The integration allows you to:
- **Track hardware visually**: Use cameras to detect pumps, sensors, relays, valves, etc.
- **Validate by location**: Match detected hardware against expected hardware at each location
- **Monitor condition**: Assess hardware condition through visual inspection
- **Manual validation**: Users manually validate detections and register devices/locations

## Key Features

### 1. Location-Based Hardware Tracking
- Links camera detections to your existing `HydroDevice.location` field
- Automatically maps detected objects to hardware types (pump, sensor, relay, etc.)
- Validates what's detected vs. what should be present

### 2. Hardware Detection Models
- **HardwareDetection**: Individual hardware items detected by camera
- **LocationHardwareInventory**: Expected hardware inventory per location
- **HardwareDetectionSummary**: Periodic summaries and reports

### 3. Integration with Hydro System
- Syncs with your existing `HydroDevice` and `HydroActuator` models
- Auto-creates expected inventory based on registered devices
- Provides validation reports comparing expected vs. detected hardware

## API Endpoints

### Core Hardware Detection
```
POST /object-detection/hardware-detection/
GET  /object-detection/hardware-detection/
PUT  /object-detection/hardware-detection/{id}/validate
```

### Location Management
```
GET  /object-detection/hardware-detection/location/{location}/status
POST /object-detection/hardware-detection/inventory/sync/{location}
```

### Hydro System Integration
```
GET  /object-detection/hardware-detection/hydro-integration/locations
GET  /object-detection/hardware-detection/hydro-integration/location/{location}/health
POST /object-detection/hardware-detection/hydro-integration/location/{location}/validate
```

## Usage Workflow

### 1. Setup Location Inventory
First, sync expected hardware inventory with your hydro devices:

```python
# Auto-sync inventory for a location
POST /object-detection/hardware-detection/inventory/sync/Greenhouse A
```

This creates expected hardware records based on your `HydroDevice` and `HydroActuator` records at that location.

### 2. Process Camera Images
Upload images and process them for hardware detection:

```python
# Step 1: Upload image for object detection
POST /object-detection/detect
{
  "file": "image.jpg",
  "model_name": "default",
  "save_to_db": true
}

# Step 2: Process detection result for hardware
POST /object-detection/hardware-detection/process-detection/{detection_result_id}
{
  "location": "Greenhouse A",
  "camera_source": "camera_1",
  "confidence_threshold": 0.5
}
```

### 3. Validate Detections
Manually validate detected hardware:

```python
PUT /object-detection/hardware-detection/{detection_id}/validate
{
  "is_validated": true,
  "validation_notes": "Pump confirmed working",
  "condition_status": "good",
  "condition_notes": "No visible damage"
}
```

### 4. Monitor Location Status
Get comprehensive status reports:

```python
# Basic location status
GET /object-detection/hardware-detection/location/Greenhouse A/status

# Detailed health report
GET /object-detection/hardware-detection/hydro-integration/location/Greenhouse A/health
```

## Hardware Type Mapping

The system automatically maps detected object classes to hardware types:

```python
{
  "pump": "pump",
  "water_pump": "water_pump",
  "motor": "pump",
  "light": "light",
  "led": "light",
  "grow_light": "light",
  "fan": "fan",
  "valve": "valve",
  "solenoid": "valve",
  "sensor": "sensor",
  "relay": "relay",
  "controller": "controller",
  "esp32": "controller",
  "tank": "tank",
  "pipe": "pipe",
  "cable": "cable"
}
```

## Data Models

### HardwareDetection
Tracks individual hardware items detected by camera:
- Links to original `DetectionResult` and `DetectionObject`
- Stores location, hardware type, confidence
- Includes validation status and condition assessment
- Bounding box coordinates for precise location

### LocationHardwareInventory
Expected hardware inventory per location:
- Links to `HydroDevice` and `HydroActuator` records
- Defines expected hardware types and quantities
- Used for validation against detections

### HardwareDetectionSummary
Periodic summaries for monitoring and reporting:
- Detection statistics by location
- Validation rates and condition summaries
- Missing/unexpected hardware counts

## Example Usage

### Python Demo Script
See `examples/hardware_detection_demo.py` for a complete example:

```python
from hardware_detection_demo import HardwareDetectionDemo

demo = HardwareDetectionDemo()

# Setup inventory for a location
demo.setup_location_inventory("Greenhouse A")

# Process an image
demo.process_image_for_hardware_detection(
    "path/to/image.jpg", 
    "Greenhouse A"
)

# Get location status
demo.get_location_status("Greenhouse A")

# Get health report
demo.get_health_report("Greenhouse A")
```

### cURL Examples

```bash
# Get hydro locations
curl -X GET "http://localhost:8000/object-detection/hardware-detection/hydro-integration/locations"

# Setup inventory for location
curl -X POST "http://localhost:8000/object-detection/hardware-detection/inventory/sync/Greenhouse%20A"

# Get location health report
curl -X GET "http://localhost:8000/object-detection/hardware-detection/hydro-integration/location/Greenhouse%20A/health"

# Get camera placement suggestions
curl -X GET "http://localhost:8000/object-detection/hardware-detection/hydro-integration/camera-placement-suggestions"
```

## Database Schema

### New Tables Created
- `hardware_detections`: Individual hardware detection records
- `location_hardware_inventory`: Expected hardware per location
- `hardware_detection_summaries`: Periodic summary reports

### Relationships
- `HardwareDetection` → `DetectionResult` (foreign key)
- `HardwareDetection` → `DetectionObject` (foreign key)
- `LocationHardwareInventory` → `HydroDevice` (foreign key)
- `LocationHardwareInventory` → `HydroActuator` (foreign key)

## Configuration

### Hardware Type Mapping
Customize the mapping in `hardware_detection_service.py`:

```python
HARDWARE_TYPE_MAPPING = {
    "your_custom_class": "your_hardware_type",
    # ... add more mappings
}
```

### Detection Confidence
Adjust confidence thresholds when processing detections:

```python
confidence_threshold = 0.5  # Adjust as needed
```

## Monitoring and Alerts

### Health Scoring
Locations receive health scores based on:
- Expected vs. detected hardware match rate
- Validation completion rate
- Hardware condition assessments

### Status Categories
- **Healthy** (score ≥ 0.8): All expected hardware detected and validated
- **Warning** (score ≥ 0.6): Some missing or unvalidated hardware
- **Critical** (score < 0.6): Significant hardware issues detected

### Recommendations
The system provides automated recommendations:
- Missing hardware alerts
- Unexpected hardware notifications
- Calibration suggestions
- Maintenance reminders

## Best Practices

### 1. Camera Placement
- Position cameras to capture all hardware at a location
- Ensure good lighting and clear view of equipment
- Use multiple cameras for large locations

### 2. Regular Validation
- Validate detections promptly for accurate tracking
- Update condition status during inspections
- Add detailed notes for maintenance history

### 3. Inventory Management
- Keep location inventory synchronized with physical changes
- Update expected quantities when adding/removing hardware
- Use descriptive names for hardware items

### 4. Monitoring Schedule
- Set up regular detection runs (daily/weekly)
- Review health reports periodically
- Address critical issues promptly

## Troubleshooting

### Common Issues

1. **No Hardware Detected**
   - Check camera positioning and image quality
   - Verify confidence threshold settings
   - Ensure hardware types are in the mapping

2. **Validation Mismatches**
   - Update location inventory if hardware changed
   - Check for hardware moved between locations
   - Verify detection accuracy

3. **Low Health Scores**
   - Review missing hardware reports
   - Validate more detections
   - Update hardware conditions

### Debug Endpoints
```bash
# Get detection statistics
GET /object-detection/hardware-detection/stats

# Get hardware type mapping
GET /object-detection/hardware-detection/hardware-mapping

# Get all locations with detections
GET /object-detection/hardware-detection/locations
```

## Future Enhancements

Potential improvements:
- Automated condition assessment using AI
- Real-time hardware monitoring alerts
- Integration with maintenance scheduling
- Mobile app for field validation
- Advanced analytics and trending

## Support

For issues or questions:
1. Check the API documentation at `/docs`
2. Review the demo script in `examples/`
3. Check logs for detailed error information
4. Verify database schema and relationships