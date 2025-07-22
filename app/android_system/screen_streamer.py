# app/android_system/screen_streamer.py
# Screen capture and streaming functionality

import asyncio
import base64
import io
import logging
import time
from typing import Dict, Set, AsyncGenerator, Callable, Optional
from PIL import Image
from app.android_system.device_manager import device_manager
from app.android_system.config import SCREEN_STREAM_CONFIG

logger = logging.getLogger(__name__)

class ScreenStreamer:
    """Manages screen streaming for Android devices"""
    
    def __init__(self):
        self.device_manager = device_manager
        self.active_streams: Dict[str, asyncio.Task] = {}
        self.connected_clients: Dict[str, Set[str]] = {}
        self.stop_events: Dict[str, asyncio.Event] = {}
        self.client_callbacks: Dict[str, Dict[str, Callable]] = {}
    
    async def start_stream(self, device_serial: str, client_id: str, callback: Callable) -> bool:
        """Start streaming screen for a specific device and client"""
        try:
            # Initialize device streaming if not already active
            if device_serial not in self.connected_clients:
                self.connected_clients[device_serial] = set()
                self.stop_events[device_serial] = asyncio.Event()
                self.client_callbacks[device_serial] = {}
                
                # Start streaming task if not already running
                if device_serial not in self.active_streams or self.active_streams[device_serial].done():
                    self.active_streams[device_serial] = asyncio.create_task(
                        self._stream_device_screen(device_serial)
                    )
                    logger.info(f"Started screen streaming for device {device_serial}")
            
            # Add client to the device's connected clients
            self.connected_clients[device_serial].add(client_id)
            self.client_callbacks[device_serial][client_id] = callback
            logger.info(f"Client {client_id} connected to stream for device {device_serial}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error starting stream for device {device_serial}, client {client_id}: {str(e)}")
            return False
    
    async def stop_stream(self, device_serial: str, client_id: str):
        """Stop streaming for a specific client"""
        try:
            if device_serial in self.connected_clients and client_id in self.connected_clients[device_serial]:
                self.connected_clients[device_serial].remove(client_id)
                
                if device_serial in self.client_callbacks and client_id in self.client_callbacks[device_serial]:
                    del self.client_callbacks[device_serial][client_id]
                
                logger.info(f"Client {client_id} disconnected from stream for device {device_serial}")
                
                # If no clients are connected to this device, stop the stream
                if not self.connected_clients[device_serial] and device_serial in self.active_streams:
                    if not self.active_streams[device_serial].done():
                        self.stop_events[device_serial].set()
                        await self.active_streams[device_serial]
                        logger.info(f"Stopped screen streaming for device {device_serial}")
                    
                    # Clean up
                    del self.active_streams[device_serial]
                    del self.connected_clients[device_serial]
                    del self.stop_events[device_serial]
                    del self.client_callbacks[device_serial]
                    
        except Exception as e:
            logger.error(f"Error stopping stream for device {device_serial}, client {client_id}: {str(e)}")
    
    async def _stream_device_screen(self, device_serial: str):
        """Stream the screen of a specific device"""
        try:
            device = self.device_manager.get_device_by_serial(device_serial)
            if not device:
                logger.error(f"Device {device_serial} not found for streaming")
                return
            
            stop_event = self.stop_events[device_serial]
            frame_count = 0
            fps = SCREEN_STREAM_CONFIG["fps"]
            quality = SCREEN_STREAM_CONFIG["quality"]
            format_type = SCREEN_STREAM_CONFIG["format"]
            
            logger.info(f"Starting screen stream for device {device_serial} at {fps} FPS")
            
            while not stop_event.is_set():
                start_time = time.time()
                frame_count += 1
                
                try:
                    # Capture screenshot
                    screenshot = device.screenshot()
                    
                    # Convert to base64 for sending over WebSocket
                    buffered = io.BytesIO()
                    screenshot.save(buffered, format=format_type, quality=quality)
                    img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
                    
                    # Prepare frame data
                    frame_data = {
                        "device_serial": device_serial,
                        "image": img_str,
                        "timestamp": time.time(),
                        "frame_count": frame_count,
                        "using_mock": self.device_manager.adb_client.is_mock,
                        "fps": fps,
                        "quality": quality
                    }
                    
                    # Send to all connected clients for this device
                    if device_serial in self.client_callbacks:
                        for client_id, callback in list(self.client_callbacks[device_serial].items()):
                            try:
                                await callback(frame_data)
                            except Exception as e:
                                logger.error(f"Error sending frame to client {client_id}: {str(e)}")
                                # Remove problematic client
                                if client_id in self.connected_clients.get(device_serial, set()):
                                    self.connected_clients[device_serial].remove(client_id)
                                if client_id in self.client_callbacks.get(device_serial, {}):
                                    del self.client_callbacks[device_serial][client_id]
                
                except Exception as e:
                    logger.error(f"Error capturing screenshot for device {device_serial}: {str(e)}")
                    await asyncio.sleep(1)  # Wait longer if there's an error
                    continue
                
                # Control frame rate
                elapsed = time.time() - start_time
                sleep_time = max(0, 1/fps - elapsed)
                await asyncio.sleep(sleep_time)
                
        except Exception as e:
            logger.error(f"Error in screen streaming for device {device_serial}: {str(e)}")
        finally:
            # Clean up
            if device_serial in self.stop_events:
                self.stop_events[device_serial].set()
    
    def get_active_streams(self) -> Dict[str, Dict[str, any]]:
        """Get information about active streams"""
        active_info = {}
        
        for device_serial, task in self.active_streams.items():
            if not task.done():
                client_count = len(self.connected_clients.get(device_serial, set()))
                active_info[device_serial] = {
                    "device_serial": device_serial,
                    "client_count": client_count,
                    "clients": list(self.connected_clients.get(device_serial, set())),
                    "running": True,
                    "fps": SCREEN_STREAM_CONFIG["fps"],
                    "quality": SCREEN_STREAM_CONFIG["quality"]
                }
        
        return active_info
    
    def get_stream_stats(self, device_serial: str) -> Optional[Dict[str, any]]:
        """Get streaming statistics for a specific device"""
        if device_serial not in self.active_streams:
            return None
        
        task = self.active_streams[device_serial]
        client_count = len(self.connected_clients.get(device_serial, set()))
        
        return {
            "device_serial": device_serial,
            "active": not task.done(),
            "client_count": client_count,
            "clients": list(self.connected_clients.get(device_serial, set())),
            "config": SCREEN_STREAM_CONFIG
        }
    
    async def stop_all_streams(self):
        """Stop all active streams"""
        logger.info("Stopping all active streams")
        
        # Set all stop events
        for stop_event in self.stop_events.values():
            stop_event.set()
        
        # Wait for all tasks to complete
        for task in self.active_streams.values():
            if not task.done():
                try:
                    await task
                except Exception as e:
                    logger.error(f"Error stopping stream task: {str(e)}")
        
        # Clear all data structures
        self.active_streams.clear()
        self.connected_clients.clear()
        self.stop_events.clear()
        self.client_callbacks.clear()
        
        logger.info("All streams stopped")
    
    async def capture_single_screenshot(self, device_serial: str) -> Optional[Dict[str, any]]:
        """Capture a single screenshot from a device"""
        try:
            device = self.device_manager.get_device_by_serial(device_serial)
            if not device:
                return None
            
            # Capture screenshot
            screenshot = device.screenshot()
            
            # Convert to base64
            buffered = io.BytesIO()
            screenshot.save(buffered, format=SCREEN_STREAM_CONFIG["format"], 
                          quality=SCREEN_STREAM_CONFIG["quality"])
            img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            return {
                "device_serial": device_serial,
                "image": img_str,
                "timestamp": time.time(),
                "using_mock": self.device_manager.adb_client.is_mock,
                "format": SCREEN_STREAM_CONFIG["format"],
                "quality": SCREEN_STREAM_CONFIG["quality"]
            }
            
        except Exception as e:
            logger.error(f"Error capturing screenshot for device {device_serial}: {str(e)}")
            return None

# Create singleton instance
screen_streamer = ScreenStreamer()