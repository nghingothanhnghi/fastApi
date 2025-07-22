# api/endpoints/screen.py
# This file defines the API endpoints for managing screen interactions with Android devices.
import asyncio
import logging
import os
import uuid
import base64
import io

from typing import Dict, List

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.android_system.device_manager import device_manager
from app.android_system.screen_streamer import screen_streamer

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/devices/{device_serial}/screenshot")
async def get_screenshot(device_serial: str):
    """
    Take a single screenshot from a device and return it as base64 encoded image.
    """
    try:
        if device_manager is None:
            raise HTTPException(status_code=500, detail="ADB client not initialized")
        
        device = device_manager.get_device_by_serial(device_serial)
        if not device:
            raise HTTPException(status_code=404, detail=f"Device {device_serial} not found")
        
        screenshot = device.screenshot()

        if not hasattr(screenshot, 'save'):
            raise HTTPException(status_code=500, detail="Invalid screenshot object")

        buffered = io.BytesIO()
        screenshot.save(buffered, format="JPEG", quality=80)
        img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')

        return {
            "status": "ok",
            "device_serial": device_serial,
            "image": img_str,
            "using_mock": device_manager.adb_client.is_mock
        }
    except Exception as e:
        logger.error(f"Error taking screenshot: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/stream/{device_serial}")
async def stream_screen(websocket: WebSocket, device_serial: str):
    """
    Stream the screen of a device over WebSocket.
    """
    await websocket.accept()
    client_id = str(uuid.uuid4())

    try:
        if device_manager is None:
            await websocket.close(code=1011, reason="ADB client not initialized")
            return
        
        device = device_manager.get_device_by_serial(device_serial)
        if not device:
            await websocket.close(code=1011, reason=f"Device {device_serial} not found")
            return

        async def send_frame(frame_data):
            await websocket.send_json(frame_data)

        frame_generator = await screen_streamer.start_stream(
            device_serial=device_serial,
            client_id=client_id,
            callback=send_frame
        )

        async for frame in frame_generator:
            if frame["client_id"] == client_id:
                await websocket.send_json(frame)

    except WebSocketDisconnect:
        logger.info(f"Client {client_id} disconnected from stream")
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {str(e)}")
        try:
            await websocket.close(code=1011, reason=str(e))
        except:
            pass
    finally:
        await screen_streamer.stop_stream(device_serial, client_id)

@router.get("/stream/status")
async def get_stream_status():
    """
    Get the status of all active streams.
    """
    active_streams = {
        device_serial: len(clients)
        for device_serial, clients in screen_streamer.connected_clients.items()
    }

    return {
        "status": "ok",
        "active_streams": active_streams,
        "using_mock": device_manager.adb_client.is_mock
    }

@router.get("/devices")
async def list_devices_with_info():
    """
    Get a list of all devices with their screen capabilities.
    """
    try:
        if device_manager is None:
            raise HTTPException(status_code=500, detail="ADB client not initialized")

        devices = device_manager.discover_devices()
        device_info = []

        for info in devices:
            try:
                serial = info.get("serial")
                if not serial:
                    continue

                device = device_manager.get_device_by_serial(serial)
                if not device:
                    raise Exception("Device not accessible")

                size_output = device.shell("wm size")
                width, height = 1080, 1920

                if "Physical size:" in size_output:
                    size_part = size_output.split("Physical size:")[1].strip()
                    if "x" in size_part:
                        width, height = map(int, size_part.split("x"))

                model = info.get("properties", {}).get("ro.product.model", "Unknown")

                device_info.append({
                    "serial": serial,
                    "model": model,
                    "screen": {
                        "width": width,
                        "height": height
                    }
                })
            except Exception as e:
                logger.error(f"Error getting device info for {info.get('serial')}: {str(e)}")
                device_info.append({
                    "serial": info.get("serial"),
                    "error": str(e)
                })

        return {
            "status": "ok",
            "devices": device_info,
            "using_mock": device_manager.adb_client.is_mock
        }

    except Exception as e:
        logger.error(f"Error listing devices with info: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
