# app/utils/connection_manager.py
# WebSocket connection manager for hardware detection real-time updates

import json
import logging
from typing import Dict, List, Set, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)

class DetectionWebSocketManager:
    """Manages WebSocket connections for hardware detection real-time updates"""
    
    def __init__(self):
        # Store active connections by connection ID
        self.active_connections: Dict[str, WebSocket] = {}
        
        # Store subscriptions by location
        self.location_subscriptions: Dict[str, Set[str]] = {}
        
        # Store subscriptions by user (if needed for user-specific updates)
        self.user_subscriptions: Dict[int, Set[str]] = {}
        
        # Store connection metadata
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
        
    async def connect(
            self, websocket: WebSocket, connection_id: str, 
            locations: Optional[List[str]] = None, 
            user_id: Optional[int] = None
            ) -> bool:
        """Accept a new WebSocket connection and set up subscriptions"""
        try:
            # Accept the WebSocket connection
            await websocket.accept()
            
            # Store the connection
            self.active_connections[connection_id] = websocket
            
            # Store metadata
            self.connection_metadata[connection_id] = {
                "connected_at": datetime.utcnow(),
                "user_id": user_id,
                "locations": locations or [],
                "last_ping": datetime.utcnow()
            }
            
            # Set up location subscriptions
            if locations:
                for location in locations:
                    self.location_subscriptions.setdefault(location, set()).add(connection_id)
        
            if user_id:
                self.user_subscriptions.setdefault(user_id, set()).add(connection_id)
        
            logger.info(f"WebSocket connection established: {connection_id}")
            
            # Send connection confirmation
            try:
                await self.send_to_connection(connection_id, {
                    "type": "connection_established",
                    "connection_id": connection_id,
                    "subscribed_locations": locations or [],
                    "timestamp": datetime.utcnow().isoformat()
                })
            except Exception as send_error:
                logger.error(f"Failed to send connection confirmation to {connection_id}: {send_error}")
                # Don't fail the connection just because we couldn't send the confirmation
            
            return True
            
        except Exception as e:
            logger.error(f"Error connecting WebSocket {connection_id}: {e}")
            # Clean up if connection failed
            await self.disconnect(connection_id)
            return False
    
    async def disconnect(self, connection_id: str):
        """Remove a WebSocket connection and clean up subscriptions"""
        try:
            # Remove from active connections
            if connection_id in self.active_connections:
                del self.active_connections[connection_id]
            
            # Clean up location subscriptions
            for location, connections in self.location_subscriptions.items():
                connections.discard(connection_id)
            
            # Clean up user subscriptions
            for user_id, connections in self.user_subscriptions.items():
                connections.discard(connection_id)
            
            # Remove metadata
            if connection_id in self.connection_metadata:
                del self.connection_metadata[connection_id]
            
            logger.info(f"WebSocket connection disconnected: {connection_id}")
            
        except Exception as e:
            logger.error(f"Error disconnecting WebSocket {connection_id}: {e}")
    
    async def send_to_connection(self, connection_id: str, data: Dict[str, Any]) -> bool:
        """Send data to a specific connection"""
        try:
            if connection_id in self.active_connections:
                websocket = self.active_connections[connection_id]
                
                # Check if websocket is still connected before sending
                if websocket.client_state.name != "CONNECTED":
                    logger.warning(f"WebSocket {connection_id} is not connected (state: {websocket.client_state.name})")
                    await self.disconnect(connection_id)
                    return False
                
                await websocket.send_text(json.dumps(data, default=str))
                return True
            return False
        except WebSocketDisconnect:
            logger.info(f"WebSocket {connection_id} disconnected during send")
            await self.disconnect(connection_id)
            return False
        except RuntimeError as e:
            if "WebSocket is not connected" in str(e) or "Need to call accept first" in str(e):
                logger.warning(f"WebSocket {connection_id} connection error: {e}")
                await self.disconnect(connection_id)
                return False
            else:
                logger.error(f"Runtime error sending to connection {connection_id}: {e}")
                await self.disconnect(connection_id)
                return False
        except Exception as e:
            logger.error(f"Error sending to connection {connection_id}: {e}")
            await self.disconnect(connection_id)
            return False
    
    async def broadcast_to_location(self, location: str, data: Dict[str, Any]):
        """Broadcast data to all connections subscribed to a specific location"""
        if location in self.location_subscriptions:
            connection_ids = list(self.location_subscriptions[location])
            
            # Send to all connections for this location
            tasks = []
            for connection_id in connection_ids:
                tasks.append(self.send_to_connection(connection_id, data))
            
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                successful = sum(1 for result in results if result is True)
                logger.info(f"Broadcasted to location '{location}': {successful}/{len(tasks)} successful")
    
    async def broadcast_to_user(self, user_id: int, data: Dict[str, Any]):
        """Broadcast data to all connections for a specific user"""
        if user_id in self.user_subscriptions:
            connection_ids = list(self.user_subscriptions[user_id])
            
            tasks = []
            for connection_id in connection_ids:
                tasks.append(self.send_to_connection(connection_id, data))
            
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                successful = sum(1 for result in results if result is True)
                logger.info(f"Broadcasted to user {user_id}: {successful}/{len(tasks)} successful")
    
    async def broadcast_to_all(self, data: Dict[str, Any]):
        """Broadcast data to all active connections"""
        if not self.active_connections:
            return
        
        connection_ids = list(self.active_connections.keys())
        tasks = []
        for connection_id in connection_ids:
            tasks.append(self.send_to_connection(connection_id, data))
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            successful = sum(1 for result in results if result is True)
            logger.info(f"Broadcasted to all connections: {successful}/{len(tasks)} successful")
    
    async def subscribe_to_location(self, connection_id: str, location: str):
        """Subscribe a connection to a specific location"""
        if connection_id in self.active_connections:
            if location not in self.location_subscriptions:
                self.location_subscriptions[location] = set()
            self.location_subscriptions[location].add(connection_id)
            
            # Update metadata
            if connection_id in self.connection_metadata:
                locations = self.connection_metadata[connection_id].get("locations", [])
                if location not in locations:
                    locations.append(location)
                    self.connection_metadata[connection_id]["locations"] = locations
            
            await self.send_to_connection(connection_id, {
                "type": "subscription_added",
                "location": location,
                "timestamp": datetime.utcnow().isoformat()
            })
    
    async def unsubscribe_from_location(self, connection_id: str, location: str):
        """Unsubscribe a connection from a specific location"""
        if location in self.location_subscriptions:
            self.location_subscriptions[location].discard(connection_id)
        
        # Update metadata
        if connection_id in self.connection_metadata:
            locations = self.connection_metadata[connection_id].get("locations", [])
            if location in locations:
                locations.remove(location)
                self.connection_metadata[connection_id]["locations"] = locations
        
        await self.send_to_connection(connection_id, {
            "type": "subscription_removed",
            "location": location,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def ping_connections(self):
        """Send ping to all connections to keep them alive"""
        if not self.active_connections:
            return
        
        ping_data = {
            "type": "ping",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_all(ping_data)
    
    async def cleanup_stale_connections(self):
        """Clean up connections that are no longer valid"""
        stale_connections = []
        
        for connection_id, websocket in list(self.active_connections.items()):
            try:
                # Check if the WebSocket is still connected
                if websocket.client_state.name != "CONNECTED":
                    stale_connections.append(connection_id)
            except Exception as e:
                logger.warning(f"Error checking connection state for {connection_id}: {e}")
                stale_connections.append(connection_id)
        
        # Remove stale connections
        for connection_id in stale_connections:
            logger.info(f"Cleaning up stale connection: {connection_id}")
            await self.disconnect(connection_id)
        
        if stale_connections:
            logger.info(f"Cleaned up {len(stale_connections)} stale connections")
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get statistics about current connections"""
        return {
            "total_connections": len(self.active_connections),
            "location_subscriptions": {
                location: len(connections) 
                for location, connections in self.location_subscriptions.items()
            },
            "user_subscriptions": {
                user_id: len(connections) 
                for user_id, connections in self.user_subscriptions.items()
            },
            "connections": [
                {
                    "connection_id": conn_id,
                    "connected_at": metadata.get("connected_at"),
                    "user_id": metadata.get("user_id"),
                    "locations": metadata.get("locations", [])
                }
                for conn_id, metadata in self.connection_metadata.items()
            ]
        }

# Global instance
detection_ws_manager = DetectionWebSocketManager()