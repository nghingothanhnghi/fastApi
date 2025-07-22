# app/android_system/device_manager.py
# Device management and discovery logic

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.utils.adb_client import adb_manager
from app.android_system.models.device import Device
from app.android_system.config import DEVICE_CONFIG

logger = logging.getLogger(__name__)

class DeviceManager:
    """Manages Android device discovery, registration, and status tracking"""
    
    def __init__(self):
        self.adb_client = adb_manager
    
    def discover_devices(self) -> List[Dict[str, Any]]:
        """Discover all connected Android devices"""
        try:
            devices = self.adb_client.get_devices()
            device_info_list = []
            
            for device in devices:
                device_info = self.adb_client.get_device_info(device)
                device_info_list.append(device_info)
            
            logger.info(f"Discovered {len(device_info_list)} devices")
            return device_info_list
            
        except Exception as e:
            logger.error(f"Error discovering devices: {str(e)}")
            return []
    
    def get_device_by_serial(self, serial: str) -> Optional[Any]:
        """Get device by serial number"""
        try:
            return self.adb_client.get_device(serial)
        except Exception as e:
            logger.error(f"Error getting device {serial}: {str(e)}")
            return None
    
    def get_device_info(self, serial: str) -> Optional[Dict[str, Any]]:
        """Get detailed device information"""
        try:
            device = self.get_device_by_serial(serial)
            if device:
                return self.adb_client.get_device_info(device)
            return None
        except Exception as e:
            logger.error(f"Error getting device info for {serial}: {str(e)}")
            return None
    
    def check_device_health(self, serial: str) -> Dict[str, Any]:
        """Check device health and connectivity"""
        try:
            device = self.get_device_by_serial(serial)
            if not device:
                return {
                    "serial": serial,
                    "healthy": False,
                    "status": "not_found",
                    "message": "Device not found"
                }
            
            # Try to execute a simple command to test connectivity
            try:
                result = device.shell("echo 'health_check'")
                healthy = "health_check" in result
            except Exception as e:
                healthy = False
                logger.error(f"Health check failed for {serial}: {str(e)}")
            
            device_info = self.adb_client.get_device_info(device)
            
            return {
                "serial": serial,
                "healthy": healthy,
                "status": device_info.get("state", "unknown"),
                "message": "Device is healthy" if healthy else "Device connectivity issues",
                "properties": device_info.get("properties", {})
            }
            
        except Exception as e:
            logger.error(f"Error checking device health for {serial}: {str(e)}")
            return {
                "serial": serial,
                "healthy": False,
                "status": "error",
                "message": str(e)
            }
    
    def register_device(self, db: Session, serial: str, name: str = None) -> Device:
        """Register a device in the database"""
        try:
            # Check if device already exists
            existing_device = db.query(Device).filter(Device.serial == serial).first()
            
            if existing_device:
                # Update existing device
                existing_device.last_seen = datetime.utcnow()
                existing_device.connection_count += 1
                existing_device.updated_at = datetime.utcnow()
                
                # Update device info
                device_info = self.get_device_info(serial)
                if device_info:
                    existing_device.status = device_info.get("state", "unknown")
                    existing_device.properties = device_info.get("properties", {})
                
                db.commit()
                db.refresh(existing_device)
                logger.info(f"Updated existing device: {serial}")
                return existing_device
            
            # Create new device
            device_info = self.get_device_info(serial)
            new_device = Device(
                serial=serial,
                name=name or f"Device {serial[-4:]}",
                status=device_info.get("state", "unknown") if device_info else "unknown",
                is_mock=self.adb_client.is_mock,
                properties=device_info.get("properties", {}) if device_info else {},
                connection_count=1
            )
            
            db.add(new_device)
            db.commit()
            db.refresh(new_device)
            logger.info(f"Registered new device: {serial}")
            return new_device
            
        except Exception as e:
            logger.error(f"Error registering device {serial}: {str(e)}")
            db.rollback()
            raise
    
    def get_registered_devices(self, db: Session) -> List[Device]:
        """Get all registered devices from database"""
        try:
            return db.query(Device).all()
        except Exception as e:
            logger.error(f"Error getting registered devices: {str(e)}")
            return []
    
    def sync_devices(self, db: Session) -> Dict[str, Any]:
        """Sync discovered devices with database"""
        try:
            discovered_devices = self.discover_devices()
            registered_devices = []
            
            for device_info in discovered_devices:
                serial = device_info.get("serial")
                if serial:
                    device = self.register_device(db, serial)
                    registered_devices.append(device.to_dict())
            
            return {
                "success": True,
                "discovered_count": len(discovered_devices),
                "registered_count": len(registered_devices),
                "devices": registered_devices
            }
            
        except Exception as e:
            logger.error(f"Error syncing devices: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "discovered_count": 0,
                "registered_count": 0,
                "devices": []
            }
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get overall ADB connection status"""
        return {
            "adb_status": self.adb_client.get_server_status(),
            "connection_check": self.adb_client.check_connection()
        }
    
    def restart_adb_server(self) -> Dict[str, Any]:
        """Restart ADB server"""
        return self.adb_client.restart_server()

# Create singleton instance
device_manager = DeviceManager()