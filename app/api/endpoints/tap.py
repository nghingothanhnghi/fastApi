from fastapi import APIRouter, Request, HTTPException
from app.android_system.interaction_controller import interaction_controller
import logging
from pydantic import BaseModel
from typing import Optional

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("")
async def tap_all(request: Request):
    try:
        data = await request.json()
        x = data.get("x")
        y = data.get("y")
        
        logger.info(f"Tapping all devices at coordinates: ({x}, {y})")
        
        result = interaction_controller.tap_all_devices(x, y)
        
        if result["success"]:
            return {"status": "ok", **result}
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
            
    except Exception as e:
        logger.error(f"Error in tap_all: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/device/{device_serial}")
async def tap_device(device_serial: str, request: Request):
    try:
        data = await request.json()
        x = data.get("x")
        y = data.get("y")
        
        logger.info(f"Tapping device {device_serial} at coordinates: ({x}, {y})")
        
        result = interaction_controller.tap_device(device_serial, x, y)
        
        if result["success"]:
            return {"status": "ok", **result}
        else:
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=result["error"])
            else:
                raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in tap_device: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/swipe")
async def swipe_all(request: Request):
    try:
        data = await request.json()
        start_x = data.get("start_x")
        start_y = data.get("start_y")
        end_x = data.get("end_x")
        end_y = data.get("end_y")
        duration_ms = data.get("duration_ms")
        
        logger.info(f"Swiping all devices from ({start_x}, {start_y}) to ({end_x}, {end_y}) with duration {duration_ms}ms")
        
        result = interaction_controller.swipe_all_devices(start_x, start_y, end_x, end_y, duration_ms)
        
        if result["success"]:
            return {"status": "ok", **result}
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
            
    except Exception as e:
        logger.error(f"Error in swipe_all: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/swipe/device/{device_serial}")
async def swipe_device(device_serial: str, request: Request):
    try:
        data = await request.json()
        start_x = data.get("start_x")
        start_y = data.get("start_y")
        end_x = data.get("end_x")
        end_y = data.get("end_y")
        duration_ms = data.get("duration_ms")
        
        logger.info(f"Swiping device {device_serial} from ({start_x}, {start_y}) to ({end_x}, {end_y}) with duration {duration_ms}ms")
        
        result = interaction_controller.swipe_device(device_serial, start_x, start_y, end_x, end_y, duration_ms)
        
        if result["success"]:
            return {"status": "ok", **result}
        else:
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=result["error"])
            else:
                raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in swipe_device: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Add new endpoints for shell commands
@router.post("/shell/device/{device_serial}")
async def execute_shell_command(device_serial: str, request: Request):
    """Execute shell command on specific device"""
    try:
        data = await request.json()
        command = data.get("command")
        
        if not command:
            raise HTTPException(status_code=400, detail="Command is required")
        
        logger.info(f"Executing shell command '{command}' on device {device_serial}")
        
        result = interaction_controller.execute_shell_command(device_serial, command)
        
        if result["success"]:
            return {"status": "ok", **result}
        else:
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=result["error"])
            else:
                raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing shell command: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
