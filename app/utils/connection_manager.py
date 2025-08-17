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
        self.active_connections: Dict[str, WebSocket] = {}
        self.location_subscriptions: Dict[str, Set[str]] = {}
        self.user_subscriptions: Dict[int, Set[str]] = {}
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
        
    async def connect(
        self,
        websocket: WebSocket,
        connection_id: str, 
        locations: Optional[List[str]] = None, 
        user_id: Optional[int] = None
    ) -> bool:
        """Register an already-accepted WebSocket connection"""
        try:

            logger.debug(f"[connect] Starting with connection_id={connection_id}, "
                        f"websocket={websocket}, state={getattr(websocket, 'client_state', None)}")

            # Make sure WebSocket is accepted before doing anything else
            await self._ensure_already_accepted(websocket)

            # Store connection
            self.active_connections[connection_id] = websocket
            
            # Store metadata
            self.connection_metadata[connection_id] = {
                "connected_at": datetime.utcnow(),
                "user_id": user_id,
                "locations": locations or [],
                "last_ping": datetime.utcnow()
            }
            
            # Subscriptions
            if locations:
                for location in locations:
                    self.location_subscriptions.setdefault(location, set()).add(connection_id)
            if user_id:
                self.user_subscriptions.setdefault(user_id, set()).add(connection_id)
            
            logger.info(f"WebSocket connection registered: {connection_id}")
            
            # Send confirmation
            await self.send_to_connection(connection_id, {
                "type": "connection_established",
                "connection_id": connection_id,
                "subscribed_locations": locations or [],
                "timestamp": datetime.utcnow().isoformat()
            })
            return True
            
        except Exception as e:
            logger.error(f"Error registering WebSocket {connection_id}: {e}")
            await self.disconnect(connection_id)
            return False
    
    async def disconnect(self, connection_id: str):
        """Remove a WebSocket connection and clean up subscriptions"""
        try:
            self.active_connections.pop(connection_id, None)
            for loc_set in self.location_subscriptions.values():
                loc_set.discard(connection_id)
            for user_set in self.user_subscriptions.values():
                user_set.discard(connection_id)
            self.connection_metadata.pop(connection_id, None)
            logger.info(f"WebSocket disconnected: {connection_id}")
        except Exception as e:
            logger.error(f"Error disconnecting {connection_id}: {e}")
    
    def _ensure_already_accepted(self, websocket: WebSocket):
        """
        Strict mode: ensure the WebSocket is already accepted.
        Raise an error if it isn't.
        """
        if websocket is None:
            logger.error("[_ensure_already_accepted] websocket is None")
            raise RuntimeError("WebSocket is None — cannot proceed")

        logger.debug(f"[_ensure_already_accepted] state={websocket.client_state.name}")
        if websocket.client_state.name != "CONNECTED":
            raise RuntimeError(
            "WebSocket has not been accepted. "
            "Call 'await websocket.accept()' before passing it to DetectionWebSocketManager.connect()."
        )

    async def send_to_connection(self, connection_id: str, data: Dict[str, Any]) -> bool:
        """Send data to a specific connection"""
        websocket = self.active_connections.get(connection_id)
        if not websocket:
            return False
        
        try:
            if websocket.client_state.name != "CONNECTED":
                logger.warning(f"WebSocket {connection_id} is stale ({websocket.client_state.name})")
                await self.disconnect(connection_id)
                return False
            await websocket.send_text(json.dumps(data, default=str))
            return True
        except (WebSocketDisconnect, RuntimeError) as e:
            logger.warning(f"WebSocket {connection_id} send failed: {e}")
            await self.disconnect(connection_id)
            return False
        except Exception as e:
            logger.error(f"Unexpected send error to {connection_id}: {e}")
            await self.disconnect(connection_id)
            return False
    
    async def broadcast_to_location(self, location: str, data: Dict[str, Any]):
        """Broadcast data to all connections subscribed to a location"""
        ids = list(self.location_subscriptions.get(location, []))
        if ids:
            results = await asyncio.gather(*(self.send_to_connection(cid, data) for cid in ids))
            logger.info(f"Broadcasted to location '{location}': {sum(results)}/{len(ids)} successful")
    
    async def broadcast_to_user(self, user_id: int, data: Dict[str, Any]):
        ids = list(self.user_subscriptions.get(user_id, []))
        if ids:
            results = await asyncio.gather(*(self.send_to_connection(cid, data) for cid in ids))
            logger.info(f"Broadcasted to user {user_id}: {sum(results)}/{len(ids)} successful")
    
    async def broadcast_to_all(self, data: Dict[str, Any]):
        ids = list(self.active_connections.keys())
        if ids:
            results = await asyncio.gather(*(self.send_to_connection(cid, data) for cid in ids))
            logger.info(f"Broadcasted to all: {sum(results)}/{len(ids)} successful")
    
    async def subscribe_to_location(self, connection_id: str, location: str):
        if connection_id in self.active_connections:
            self.location_subscriptions.setdefault(location, set()).add(connection_id)
            if connection_id in self.connection_metadata:
                locs = self.connection_metadata[connection_id].setdefault("locations", [])
                if location not in locs:
                    locs.append(location)
            await self.send_to_connection(connection_id, {
                "type": "subscription_added",
                "location": location,
                "timestamp": datetime.utcnow().isoformat()
            })
    
    async def unsubscribe_from_location(self, connection_id: str, location: str):
        self.location_subscriptions.get(location, set()).discard(connection_id)
        if connection_id in self.connection_metadata:
            locs = self.connection_metadata[connection_id].get("locations", [])
            if location in locs:
                locs.remove(location)
        await self.send_to_connection(connection_id, {
            "type": "subscription_removed",
            "location": location,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def ping_connections(self):
        await self.broadcast_to_all({
            "type": "ping",
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def cleanup_stale_connections(self):
        stale = [cid for cid, ws in self.active_connections.items()
                 if ws.client_state.name != "CONNECTED"]
        for cid in stale:
            await self.disconnect(cid)
        if stale:
            logger.info(f"Cleaned up {len(stale)} stale connections")
    
    def get_connection_stats(self) -> Dict[str, Any]:
        return {
            "total_connections": len(self.active_connections),
            "location_subscriptions": {loc: len(conns) for loc, conns in self.location_subscriptions.items()},
            "user_subscriptions": {uid: len(conns) for uid, conns in self.user_subscriptions.items()},
            "connections": [
                {
                    "connection_id": cid,
                    "connected_at": meta.get("connected_at"),
                    "user_id": meta.get("user_id"),
                    "locations": meta.get("locations", [])
                }
                for cid, meta in self.connection_metadata.items()
            ]
        }

# Global instance
detection_ws_manager = DetectionWebSocketManager()
