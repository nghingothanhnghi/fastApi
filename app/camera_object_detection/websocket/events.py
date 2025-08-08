# app/camera_object_detection/websocket/events.py
# Event system for broadcasting hardware detection updates

import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

from app.utils.connection_manager import detection_ws_manager

from app.core.logging_config import get_logger

logger = get_logger(__name__)

class HardwareDetectionEventType(Enum):
    """Types of hardware detection events"""
    NEW_DETECTION = "new_detection"
    DETECTION_VALIDATED = "detection_validated"
    DETECTION_UPDATED = "detection_updated"
    LOCATION_STATUS_CHANGED = "location_status_changed"
    INVENTORY_UPDATED = "inventory_updated"
    HYDRO_DEVICE_MATCHED = "hydro_device_matched"
    BULK_DETECTIONS_CREATED = "bulk_detections_created"
    DETECTION_PROCESSED = "detection_processed"
    STATS_UPDATED = "stats_updated"

class HardwareDetectionEventBroadcaster:
    """Handles broadcasting of hardware detection events via WebSocket"""
    
    def __init__(self):
        self.ws_manager = detection_ws_manager
    
    async def broadcast_new_detection(self, detection_data: Dict[str, Any], location: str):
        """Broadcast when a new hardware detection is created"""
        event_data = {
            "type": HardwareDetectionEventType.NEW_DETECTION.value,
            "data": detection_data,
            "location": location,
            "timestamp": datetime.utcnow().isoformat(),
            "message": f"New hardware detected at {location}"
        }
        
        # Broadcast to location subscribers
        await self.ws_manager.broadcast_to_location(location, event_data)
        
        logger.info(f"Broadcasted new detection event for location: {location}")
    
    async def broadcast_detection_validated(self, detection_data: Dict[str, Any], 
                                          location: str, validation_status: bool):
        """Broadcast when a detection is validated"""
        event_data = {
            "type": HardwareDetectionEventType.DETECTION_VALIDATED.value,
            "data": detection_data,
            "location": location,
            "validation_status": validation_status,
            "timestamp": datetime.utcnow().isoformat(),
            "message": f"Detection {'validated' if validation_status else 'invalidated'} at {location}"
        }
        
        await self.ws_manager.broadcast_to_location(location, event_data)
        
        logger.info(f"Broadcasted validation event for location: {location}")
    
    async def broadcast_bulk_detections(self, detections_data: List[Dict[str, Any]], 
                                      location: str, count: int):
        """Broadcast when bulk detections are created"""
        event_data = {
            "type": HardwareDetectionEventType.BULK_DETECTIONS_CREATED.value,
            "data": detections_data,
            "location": location,
            "count": count,
            "timestamp": datetime.utcnow().isoformat(),
            "message": f"{count} new detections created at {location}"
        }
        
        await self.ws_manager.broadcast_to_location(location, event_data)
        
        logger.info(f"Broadcasted bulk detections event: {count} detections at {location}")
    
    async def broadcast_detection_processed(self, detections_data: List[Dict[str, Any]], 
                                          location: str, detection_result_id: int):
        """Broadcast when a detection result is processed for hardware"""
        event_data = {
            "type": HardwareDetectionEventType.DETECTION_PROCESSED.value,
            "data": detections_data,
            "location": location,
            "detection_result_id": detection_result_id,
            "count": len(detections_data),
            "timestamp": datetime.utcnow().isoformat(),
            "message": f"Detection result {detection_result_id} processed at {location}"
        }
        
        await self.ws_manager.broadcast_to_location(location, event_data)
        
        logger.info(f"Broadcasted detection processed event for result {detection_result_id}")
    
    async def broadcast_location_status_change(self, location: str, status_data: Dict[str, Any]):
        """Broadcast when location status changes"""
        event_data = {
            "type": HardwareDetectionEventType.LOCATION_STATUS_CHANGED.value,
            "data": status_data,
            "location": location,
            "timestamp": datetime.utcnow().isoformat(),
            "message": f"Status updated for location {location}"
        }
        
        await self.ws_manager.broadcast_to_location(location, event_data)
        
        logger.info(f"Broadcasted location status change for: {location}")
    
    async def broadcast_inventory_updated(self, location: str, inventory_data: Dict[str, Any]):
        """Broadcast when location inventory is updated"""
        event_data = {
            "type": HardwareDetectionEventType.INVENTORY_UPDATED.value,
            "data": inventory_data,
            "location": location,
            "timestamp": datetime.utcnow().isoformat(),
            "message": f"Inventory updated for location {location}"
        }
        
        await self.ws_manager.broadcast_to_location(location, event_data)
        
        logger.info(f"Broadcasted inventory update for location: {location}")
    
    async def broadcast_hydro_device_matched(self, detection_data: Dict[str, Any], 
                                           hydro_device_data: Dict[str, Any], location: str):
        """Broadcast when a detection is matched with a hydro device"""
        event_data = {
            "type": HardwareDetectionEventType.HYDRO_DEVICE_MATCHED.value,
            "data": {
                "detection": detection_data,
                "hydro_device": hydro_device_data
            },
            "location": location,
            "timestamp": datetime.utcnow().isoformat(),
            "message": f"Hardware detection matched with hydro device at {location}"
        }
        
        await self.ws_manager.broadcast_to_location(location, event_data)
        
        logger.info(f"Broadcasted hydro device match for location: {location}")
    
    async def broadcast_stats_updated(self, stats_data: Dict[str, Any]):
        """Broadcast when overall stats are updated"""
        event_data = {
            "type": HardwareDetectionEventType.STATS_UPDATED.value,
            "data": stats_data,
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Hardware detection statistics updated"
        }
        
        # Broadcast to all connections
        await self.ws_manager.broadcast_to_all(event_data)
        
        logger.info("Broadcasted stats update to all connections")
    
    async def broadcast_custom_event(self, event_type: str, data: Dict[str, Any], 
                                   location: Optional[str] = None, 
                                   user_id: Optional[int] = None,
                                   message: Optional[str] = None):
        """Broadcast a custom event"""
        event_data = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
            "message": message or f"Custom event: {event_type}"
        }
        
        if location:
            event_data["location"] = location
        
        # Determine broadcast target
        if location:
            await self.ws_manager.broadcast_to_location(location, event_data)
        elif user_id:
            await self.ws_manager.broadcast_to_user(user_id, event_data)
        else:
            await self.ws_manager.broadcast_to_all(event_data)
        
        logger.info(f"Broadcasted custom event: {event_type}")

# Global instance
hardware_detection_broadcaster = HardwareDetectionEventBroadcaster()

# Convenience functions for easy import and use
async def broadcast_new_detection(detection_data: Dict[str, Any], location: str):
    """Convenience function to broadcast new detection"""
    await hardware_detection_broadcaster.broadcast_new_detection(detection_data, location)

async def broadcast_detection_validated(detection_data: Dict[str, Any], 
                                      location: str, validation_status: bool):
    """Convenience function to broadcast detection validation"""
    await hardware_detection_broadcaster.broadcast_detection_validated(
        detection_data, location, validation_status
    )

async def broadcast_bulk_detections(detections_data: List[Dict[str, Any]], 
                                  location: str, count: int):
    """Convenience function to broadcast bulk detections"""
    await hardware_detection_broadcaster.broadcast_bulk_detections(
        detections_data, location, count
    )

async def broadcast_detection_processed(detections_data: List[Dict[str, Any]], 
                                      location: str, detection_result_id: int):
    """Convenience function to broadcast detection processed"""
    await hardware_detection_broadcaster.broadcast_detection_processed(
        detections_data, location, detection_result_id
    )

async def broadcast_location_status_change(location: str, status_data: Dict[str, Any]):
    """Convenience function to broadcast location status change"""
    await hardware_detection_broadcaster.broadcast_location_status_change(location, status_data)

async def broadcast_inventory_updated(location: str, inventory_data: Dict[str, Any]):
    """Convenience function to broadcast inventory update"""
    await hardware_detection_broadcaster.broadcast_inventory_updated(location, inventory_data)

async def broadcast_hydro_device_matched(detection_data: Dict[str, Any], 
                                       hydro_device_data: Dict[str, Any], location: str):
    """Convenience function to broadcast hydro device match"""
    await hardware_detection_broadcaster.broadcast_hydro_device_matched(
        detection_data, hydro_device_data, location
    )

async def broadcast_stats_updated(stats_data: Dict[str, Any]):
    """Convenience function to broadcast stats update"""
    await hardware_detection_broadcaster.broadcast_stats_updated(stats_data)