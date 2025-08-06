# app/camera_object_detection/websocket/background_tasks.py
# Background tasks for periodic WebSocket updates

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from app.database import SessionLocal
from .connection_manager import detection_ws_manager
from .events import hardware_detection_broadcaster
from ..services.hardware_detection_service import hardware_detection_service

logger = logging.getLogger(__name__)

class AsyncBackgroundTaskManager:
    """Background tasks for hardware detection WebSocket updates"""
    
    def __init__(self):
        self.running = False
        self.tasks = []
    
    async def start_background_tasks(self):
        """Start all background tasks"""
        if self.running:
            return
        
        self.running = True
        
        # Start periodic tasks
        self.tasks = [
            asyncio.create_task(self._periodic_ping()),
            asyncio.create_task(self._periodic_stats_update()),
            asyncio.create_task(self._periodic_location_status_update()),
        ]
        
        logger.info("Hardware detection background tasks started")
    
    async def stop_background_tasks(self):
        """Stop all background tasks"""
        self.running = False
        
        for task in self.tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        self.tasks = []
        logger.info("Hardware detection background tasks stopped")
    
    async def _periodic_ping(self):
        """Send periodic ping to keep connections alive"""
        while self.running:
            try:
                await detection_ws_manager.ping_connections()
                await asyncio.sleep(30)  # Ping every 30 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic ping: {e}")
                await asyncio.sleep(30)
    
    async def _periodic_stats_update(self):
        """Send periodic statistics updates"""
        while self.running:
            try:
                # Only send stats if there are active connections
                if detection_ws_manager.active_connections:
                    db = SessionLocal()
                    try:
                        stats = hardware_detection_service.get_hardware_detection_stats(db)
                        stats_data = stats.dict() if hasattr(stats, 'dict') else stats
                        
                        await hardware_detection_broadcaster.broadcast_stats_updated(stats_data)
                    finally:
                        db.close()
                
                await asyncio.sleep(300)  # Update stats every 5 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic stats update: {e}")
                await asyncio.sleep(300)
    
    async def _periodic_location_status_update(self):
        """Send periodic location status updates"""
        while self.running:
            try:
                # Only update if there are location subscriptions
                if detection_ws_manager.location_subscriptions:
                    db = SessionLocal()
                    try:
                        # Update status for each subscribed location
                        for location in detection_ws_manager.location_subscriptions.keys():
                            try:
                                status = hardware_detection_service.get_location_status(db, location)
                                status_data = status.dict() if hasattr(status, 'dict') else status
                                
                                await hardware_detection_broadcaster.broadcast_location_status_change(
                                    location, status_data
                                )
                            except Exception as e:
                                logger.warning(f"Could not update status for location {location}: {e}")
                    finally:
                        db.close()
                
                await asyncio.sleep(600)  # Update location status every 10 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic location status update: {e}")
                await asyncio.sleep(600)

# Global instance
detection_bg_tasks = AsyncBackgroundTaskManager()

# Convenience functions
async def start_hardware_detection_background_tasks():
    """Start hardware detection background tasks"""
    await detection_bg_tasks.start_background_tasks()

async def stop_hardware_detection_background_tasks():
    """Stop hardware detection background tasks"""
    await detection_bg_tasks.stop_background_tasks()