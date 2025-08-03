# app/camera_object_detection/utils/hydro_integration.py
# Utility functions for integrating camera detection with hydro system

from sqlalchemy.orm import Session
from typing import List, Dict, Optional, Tuple
import logging

from app.hydro_system.models.device import HydroDevice
from app.hydro_system.models.actuator import HydroActuator
from ..models.hardware_detection import HardwareDetection, LocationHardwareInventory
from ..services.hardware_detection_service import hardware_detection_service
from ..schemas.hardware_detection import LocationHardwareInventoryCreate

logger = logging.getLogger(__name__)


class HydroIntegrationUtils:
    """Utility class for integrating camera detection with hydro system"""
    
    @staticmethod
    def get_hydro_locations(db: Session) -> List[str]:
        """Get all unique locations from hydro devices"""
        locations = db.query(HydroDevice.location).filter(
            HydroDevice.location.isnot(None),
            HydroDevice.is_active == True
        ).distinct().all()
        
        return [location[0] for location in locations if location[0]]
    
    @staticmethod
    def get_devices_at_location(db: Session, location: str) -> List[HydroDevice]:
        """Get all hydro devices at a specific location"""
        return db.query(HydroDevice).filter(
            HydroDevice.location == location,
            HydroDevice.is_active == True
        ).all()
    
    @staticmethod
    def get_expected_hardware_at_location(db: Session, location: str) -> Dict[str, int]:
        """Get expected hardware counts at a location based on hydro devices"""
        devices = HydroIntegrationUtils.get_devices_at_location(db, location)
        
        hardware_counts = {}
        
        # Count controllers (one per device)
        if devices:
            hardware_counts["controller"] = len(devices)
        
        # Count actuators by type
        for device in devices:
            for actuator in device.actuators:
                if actuator.is_active:
                    hw_type = actuator.type
                    hardware_counts[hw_type] = hardware_counts.get(hw_type, 0) + 1
        
        return hardware_counts
    
    @staticmethod
    def validate_detection_against_hydro_system(
        db: Session,
        location: str,
        detected_hardware: List[HardwareDetection]
    ) -> Dict[str, any]:
        """
        Validate detected hardware against expected hardware from hydro system
        Returns validation report
        """
        expected_hardware = HydroIntegrationUtils.get_expected_hardware_at_location(db, location)
        
        # Count detected hardware by type
        detected_counts = {}
        for detection in detected_hardware:
            hw_type = detection.hardware_type
            detected_counts[hw_type] = detected_counts.get(hw_type, 0) + 1
        
        # Compare expected vs detected
        validation_report = {
            "location": location,
            "expected_hardware": expected_hardware,
            "detected_hardware": detected_counts,
            "missing_hardware": [],
            "unexpected_hardware": [],
            "correct_detections": [],
            "validation_score": 0.0
        }
        
        # Find missing hardware
        for hw_type, expected_count in expected_hardware.items():
            detected_count = detected_counts.get(hw_type, 0)
            if detected_count < expected_count:
                validation_report["missing_hardware"].append({
                    "type": hw_type,
                    "expected": expected_count,
                    "detected": detected_count,
                    "missing": expected_count - detected_count
                })
            elif detected_count == expected_count:
                validation_report["correct_detections"].append({
                    "type": hw_type,
                    "count": detected_count
                })
        
        # Find unexpected hardware
        for hw_type, detected_count in detected_counts.items():
            expected_count = expected_hardware.get(hw_type, 0)
            if detected_count > expected_count:
                validation_report["unexpected_hardware"].append({
                    "type": hw_type,
                    "expected": expected_count,
                    "detected": detected_count,
                    "unexpected": detected_count - expected_count
                })
        
        # Calculate validation score (0-1)
        total_expected = sum(expected_hardware.values())
        total_correct = sum(item["count"] for item in validation_report["correct_detections"])
        
        if total_expected > 0:
            validation_report["validation_score"] = total_correct / total_expected
        else:
            validation_report["validation_score"] = 1.0 if not detected_counts else 0.0
        
        return validation_report
    
    @staticmethod
    def auto_setup_location_inventory(db: Session, location: str) -> List[LocationHardwareInventory]:
        """
        Automatically set up expected hardware inventory for a location
        based on hydro devices and actuators
        """
        # Check if inventory already exists
        existing_inventory = db.query(LocationHardwareInventory).filter(
            LocationHardwareInventory.location == location,
            LocationHardwareInventory.is_active == True
        ).all()
        
        if existing_inventory:
            logger.info(f"Inventory already exists for location {location}")
            return existing_inventory
        
        # Create inventory based on hydro devices
        return hardware_detection_service.sync_location_inventory_with_hydro_devices(db, location)
    
    @staticmethod
    def get_location_health_report(db: Session, location: str) -> Dict[str, any]:
        """
        Generate a comprehensive health report for a location
        combining hydro system data and detection data
        """
        # Get hydro devices at location
        hydro_devices = HydroIntegrationUtils.get_devices_at_location(db, location)
        
        # Get recent hardware detections
        from datetime import datetime, timedelta
        recent_cutoff = datetime.utcnow() - timedelta(hours=24)
        
        recent_detections = db.query(HardwareDetection).filter(
            HardwareDetection.location == location,
            HardwareDetection.detected_at >= recent_cutoff
        ).all()
        
        # Get validation report
        validation_report = HydroIntegrationUtils.validate_detection_against_hydro_system(
            db, location, recent_detections
        )
        
        # Compile health report
        health_report = {
            "location": location,
            "timestamp": datetime.utcnow(),
            "hydro_system": {
                "device_count": len(hydro_devices),
                "active_devices": len([d for d in hydro_devices if d.is_active]),
                "total_actuators": sum(len(d.actuators) for d in hydro_devices),
                "active_actuators": sum(len([a for a in d.actuators if a.is_active]) for d in hydro_devices),
                "devices": [
                    {
                        "id": d.id,
                        "name": d.name,
                        "device_id": d.device_id,
                        "is_active": d.is_active,
                        "actuator_count": len(d.actuators)
                    }
                    for d in hydro_devices
                ]
            },
            "detection_system": {
                "recent_detections": len(recent_detections),
                "validated_detections": len([d for d in recent_detections if d.is_validated]),
                "average_confidence": (
                    sum(d.confidence for d in recent_detections) / len(recent_detections)
                    if recent_detections else 0.0
                ),
                "hardware_types_detected": list(set(d.hardware_type for d in recent_detections)),
                "condition_summary": {
                    "good": len([d for d in recent_detections if d.condition_status == "good"]),
                    "damaged": len([d for d in recent_detections if d.condition_status == "damaged"]),
                    "unknown": len([d for d in recent_detections if d.condition_status == "unknown"]),
                }
            },
            "validation": validation_report,
            "overall_health": {
                "score": validation_report["validation_score"],
                "status": "healthy" if validation_report["validation_score"] >= 0.8 else 
                         "warning" if validation_report["validation_score"] >= 0.6 else "critical",
                "issues": len(validation_report["missing_hardware"]) + len(validation_report["unexpected_hardware"]),
                "recommendations": HydroIntegrationUtils._generate_recommendations(validation_report)
            }
        }
        
        return health_report
    
    @staticmethod
    def _generate_recommendations(validation_report: Dict[str, any]) -> List[str]:
        """Generate recommendations based on validation report"""
        recommendations = []
        
        if validation_report["missing_hardware"]:
            recommendations.append(
                f"Check for missing hardware: {', '.join([item['type'] for item in validation_report['missing_hardware']])}"
            )
        
        if validation_report["unexpected_hardware"]:
            recommendations.append(
                f"Verify unexpected hardware: {', '.join([item['type'] for item in validation_report['unexpected_hardware']])}"
            )
        
        if validation_report["validation_score"] < 0.6:
            recommendations.append("Consider recalibrating camera detection or updating hardware inventory")
        
        if not recommendations:
            recommendations.append("System appears to be functioning normally")
        
        return recommendations
    
    @staticmethod
    def suggest_camera_placement(db: Session) -> List[Dict[str, any]]:
        """
        Suggest optimal camera placement based on hydro device locations
        """
        locations = HydroIntegrationUtils.get_hydro_locations(db)
        
        suggestions = []
        for location in locations:
            devices = HydroIntegrationUtils.get_devices_at_location(db, location)
            expected_hardware = HydroIntegrationUtils.get_expected_hardware_at_location(db, location)
            
            # Check if location has detection coverage
            recent_detections = db.query(HardwareDetection).filter(
                HardwareDetection.location == location
            ).count()
            
            suggestion = {
                "location": location,
                "device_count": len(devices),
                "expected_hardware_types": list(expected_hardware.keys()),
                "total_hardware_items": sum(expected_hardware.values()),
                "has_detection_coverage": recent_detections > 0,
                "priority": "high" if not recent_detections and len(devices) > 0 else "medium",
                "recommendation": (
                    f"Install camera to monitor {sum(expected_hardware.values())} hardware items"
                    if not recent_detections else
                    "Camera coverage appears adequate"
                )
            }
            
            suggestions.append(suggestion)
        
        # Sort by priority
        priority_order = {"high": 3, "medium": 2, "low": 1}
        suggestions.sort(key=lambda x: priority_order.get(x["priority"], 0), reverse=True)
        
        return suggestions


# Export utility instance
hydro_integration = HydroIntegrationUtils()