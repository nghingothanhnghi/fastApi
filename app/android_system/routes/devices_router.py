from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.android_system.device_manager import device_manager
from app.database import get_db
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("")
def list_devices():
    try:
        # Get discovered devices
        devices = device_manager.discover_devices()
        device_serials = [device.get("serial") for device in devices if device.get("serial")]
        
        return {
            "status": "ok", 
            "message": f"Found {len(devices)} devices", 
            "devices": device_serials,
            "device_details": devices
        }
    except Exception as e:
        logger.error(f"Error listing devices: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
def get_adb_status():
    """Get detailed ADB status information"""
    try:
        connection_status = device_manager.get_connection_status()
        return {
            "status": "ok",
            **connection_status["adb_status"]
        }
    except Exception as e:
        logger.error(f"Error getting ADB status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/details")
def get_device_details():
    """Get detailed information about all connected devices"""
    try:
        devices = device_manager.discover_devices()
        
        return {
            "status": "ok",
            "count": len(devices),
            "devices": devices,
            "using_mock": device_manager.adb_client.is_mock
        }
    except Exception as e:
        logger.error(f"Error getting device details: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/restart-adb")
def restart_adb():
    """Restart ADB server"""
    try:
        result = device_manager.restart_adb_server()
        if result.get("success", False):
            return {"status": "ok", **result}
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
    except Exception as e:
        logger.error(f"Error restarting ADB: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
@router.get("/{device_serial}")
def get_device_detail(device_serial: str):
    """Get detailed information about a specific device"""
    try:
        device_info = device_manager.get_device_info(device_serial)
        if not device_info:
            raise HTTPException(status_code=404, detail=f"Device {device_serial} not found")
        
        return {
            "status": "ok",
            "device": device_info,
            "using_mock": device_manager.adb_client.is_mock
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting device detail: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/register")
def register_device(serial: str, name: str = None, db: Session = Depends(get_db)):
    """Register a device in the database"""
    try:
        device = device_manager.register_device(db, serial, name)
        return {"status": "ok", "device": device.to_dict()}
    except Exception as e:
        logger.error(f"Error registering device: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/registered/list")
def get_registered_devices(db: Session = Depends(get_db)):
    """Get all registered devices from database"""
    try:
        devices = device_manager.get_registered_devices(db)
        return {
            "status": "ok",
            "count": len(devices),
            "devices": [device.to_dict() for device in devices]
        }
    except Exception as e:
        logger.error(f"Error getting registered devices: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sync")
def sync_devices(db: Session = Depends(get_db)):
    """Sync discovered devices with database"""
    try:
        result = device_manager.sync_devices(db)
        return {"status": "ok", **result}
    except Exception as e:
        logger.error(f"Error syncing devices: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{device_serial}/health")
def check_device_health(device_serial: str):
    """Check device health and connectivity"""
    try:
        health_info = device_manager.check_device_health(device_serial)
        return {"status": "ok", **health_info}
    except Exception as e:
        logger.error(f"Error checking device health: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

