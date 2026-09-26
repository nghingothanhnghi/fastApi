# app/camera_object_detection/routes/ws_router.py
# WebSocket router for hardware detection real-time updates

# import json
# import uuid
# import logging
# from typing import List, Optional
# from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
# from sqlalchemy.orm import Session

# from app.database import get_db
# from app.utils.connection_manager import detection_ws_manager
# from app.camera_object_detection.services.hardware_detection_service import hardware_detection_service

# logger = logging.getLogger(__name__)

# router = APIRouter(prefix="/ws", tags=["Hardware Detection WebSocket"])

# @router.websocket("/hardware-detection")
# async def hardware_detection_websocket(
#     websocket: WebSocket,
#     locations: Optional[str] = Query(None, description="Comma-separated list of locations to subscribe to"),
#     user_id: Optional[int] = Query(None, description="User ID for user-specific updates"),
#     db: Session = Depends(get_db)
# ):
#     """
#     WebSocket endpoint for real-time hardware detection updates
    
#     Query Parameters:
#     - locations: Comma-separated list of locations to subscribe to (e.g., "greenhouse_a,greenhouse_b")
#     - user_id: User ID for user-specific updates
    
#     Message Types Sent:
#     - connection_established: Sent when connection is established
#     - new_detection: New hardware detection created
#     - detection_validated: Detection validation status changed
#     - bulk_detections_created: Multiple detections created at once
#     - detection_processed: Detection result processed for hardware
#     - location_status_changed: Location status updated
#     - inventory_updated: Location inventory updated
#     - hydro_device_matched: Detection matched with hydro device
#     - stats_updated: Overall statistics updated
#     - ping: Keep-alive ping
#     - error: Error message
    
#     Message Types Received:
#     - subscribe_location: Subscribe to a location
#     - unsubscribe_location: Unsubscribe from a location
#     - get_location_status: Get current status for a location
#     - get_stats: Get current statistics
#     - pong: Response to ping
#     """

#         # Accept the WebSocket connection before doing anything else
#     try:
#         await websocket.accept()
#     except Exception as e:
#         logger.error(f"Failed to accept WebSocket connection: {e}")
#         return
    
#     # Generate unique connection ID
#     connection_id = str(uuid.uuid4())
    
#     # Parse locations
#     location_list = []
#     if locations:
#         location_list = [loc.strip() for loc in locations.split(",") if loc.strip()]
    
#     try:
#         # Establish connection
#         success = await detection_ws_manager.connect(
#             websocket, connection_id, location_list, user_id
#         )
        
#         if not success:
#             try:
#                 await websocket.close(code=1000, reason="Failed to establish connection")
#             except Exception as close_error:
#                 logger.error(f"Error closing WebSocket after failed connection: {close_error}")
#             return
        
#         # Send initial data if locations are specified
#         if location_list:
#             for location in location_list:
#                 try:
#                     # Send current location status
#                     status = hardware_detection_service.get_location_status(db, location)
#                     await detection_ws_manager.send_to_connection(connection_id, {
#                         "type": "initial_location_status",
#                         "location": location,
#                         "data": status.dict() if hasattr(status, 'dict') else status,
#                         "timestamp": None
#                     })
#                 except Exception as e:
#                     logger.warning(f"Could not send initial status for location {location}: {e}")
        
#         # Listen for messages
#         while True:
#             try:
#                 # Receive message from client
#                 data = await websocket.receive_text()
#                 message = json.loads(data)
                
#                 message_type = message.get("type")
                
#                 if message_type == "subscribe_location":
#                     location = message.get("location")
#                     if location:
#                         await detection_ws_manager.subscribe_to_location(
#                             connection_id, location
#                         )
                        
#                         # Send current location status
#                         try:
#                             status = hardware_detection_service.get_location_status(db, location)
#                             await detection_ws_manager.send_to_connection(connection_id, {
#                                 "type": "location_status",
#                                 "location": location,
#                                 "data": status.dict() if hasattr(status, 'dict') else status,
#                                 "timestamp": None
#                             })
#                         except Exception as e:
#                             logger.warning(f"Could not send status for location {location}: {e}")
                
#                 elif message_type == "unsubscribe_location":
#                     location = message.get("location")
#                     if location:
#                         await detection_ws_manager.unsubscribe_from_location(
#                             connection_id, location
#                         )
                
#                 elif message_type == "get_location_status":
#                     location = message.get("location")
#                     if location:
#                         try:
#                             status = hardware_detection_service.get_location_status(db, location)
#                             await detection_ws_manager.send_to_connection(connection_id, {
#                                 "type": "location_status",
#                                 "location": location,
#                                 "data": status.dict() if hasattr(status, 'dict') else status,
#                                 "timestamp": None
#                             })
#                         except Exception as e:
#                             # Only send error if connection is still active
#                             if connection_id in detection_ws_manager.active_connections:
#                                 await detection_ws_manager.send_to_connection(connection_id, {
#                                     "type": "error",
#                                     "message": f"Could not get status for location {location}: {str(e)}",
#                                     "timestamp": None
#                                 })
                
#                 elif message_type == "get_stats":
#                     try:
#                         stats = hardware_detection_service.get_hardware_detection_stats(db)
#                         await detection_ws_manager.send_to_connection(connection_id, {
#                             "type": "stats",
#                             "data": stats.dict() if hasattr(stats, 'dict') else stats,
#                             "timestamp": None
#                         })
#                     except Exception as e:
#                         # Only send error if connection is still active
#                         if connection_id in detection_ws_manager.active_connections:
#                             await detection_ws_manager.send_to_connection(connection_id, {
#                                 "type": "error",
#                                 "message": f"Could not get stats: {str(e)}",
#                                 "timestamp": None
#                             })
                
#                 elif message_type == "pong":
#                     # Client responded to ping
#                     logger.debug(f"Received pong from connection {connection_id}")
                
#                 else:
#                     # Only send error if connection is still active
#                     if connection_id in detection_ws_manager.active_connections:
#                         await detection_ws_manager.send_to_connection(connection_id, {
#                             "type": "error",
#                             "message": f"Unknown message type: {message_type}",
#                             "timestamp": None
#                         })
                    
#             except json.JSONDecodeError:
#                 # Only send error if connection is still active
#                 if connection_id in detection_ws_manager.active_connections:
#                     await detection_ws_manager.send_to_connection(connection_id, {
#                         "type": "error",
#                         "message": "Invalid JSON format",
#                         "timestamp": None
#                     })
#             except WebSocketDisconnect:
#                 break
#             except Exception as e:
#                 logger.error(f"Error handling WebSocket message: {e}")
#                 # Only try to send error if connection is still active
#                 if connection_id in detection_ws_manager.active_connections:
#                     try:
#                         await detection_ws_manager.send_to_connection(connection_id, {
#                             "type": "error",
#                             "message": f"Server error: {str(e)}",
#                             "timestamp": None
#                         })
#                     except Exception as send_error:
#                         logger.error(f"Failed to send error message to WebSocket {connection_id}: {send_error}")
#                         break  # Exit the loop if we can't send messages
#                 else:
#                     # Connection is no longer active, exit the loop
#                     logger.warning(f"Connection {connection_id} is no longer active, exiting message loop")
#                     break
    
#     except WebSocketDisconnect:
#         logger.info(f"WebSocket disconnected: {connection_id}")
#     except Exception as e:
#         logger.error(f"WebSocket error for connection {connection_id}: {e}")
#     finally:
#         await detection_ws_manager.disconnect(connection_id)

# @router.get("/connections/stats")
# async def get_websocket_stats():
#     """Get statistics about current WebSocket connections"""
#     return detection_ws_manager.get_connection_stats()

# @router.post("/test-broadcast")
# async def test_broadcast(
#     location: str,
#     message: str = "Test message",
#     db: Session = Depends(get_db)
# ):
#     """Test endpoint to broadcast a message to a specific location"""
#     from .events import hardware_detection_broadcaster
    
#     test_data = {
#         "test": True,
#         "message": message,
#         "location": location
#     }
    
#     await hardware_detection_broadcaster.broadcast_custom_event(
#         "test_broadcast", test_data, location, message=f"Test broadcast to {location}"
#     )
    
#     return {"message": f"Test broadcast sent to location: {location}"}

# @router.post("/ping-all")
# async def ping_all_connections():
#     """Send ping to all WebSocket connections"""
#     await detection_ws_manager.ping_connections()
#     return {"message": "Ping sent to all connections"}

# app/camera_object_detection/routes/ws_router.py
# WebSocket router for hardware detection real-time updates

import json
import uuid
import logging
from typing import List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.utils.connection_manager import detection_ws_manager
from app.camera_object_detection.services.hardware_detection_service import hardware_detection_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["Hardware Detection WebSocket"])


def _get_location_status_safely(location: str):
    """
    Open a short-lived DB session for exactly one query, then close it.

    IMPORTANT: the websocket handler below used to receive a single
    `db: Session = Depends(get_db)` for its entire connected lifetime.
    Since a websocket can stay open for minutes or hours, that pinned one
    connection out of the pool (size=5, overflow=10) per open tab. A
    handful of open dashboards was enough to exhaust the pool and start
    timing out unrelated requests elsewhere in the app (see the
    `QueuePool limit ... reached` errors). Opening/closing a session per
    operation, right here, fixes that while keeping identical behavior.
    """
    db = SessionLocal()
    try:
        return hardware_detection_service.get_location_status(db, location)
    finally:
        db.close()


def _get_hardware_detection_stats_safely():
    db = SessionLocal()
    try:
        return hardware_detection_service.get_hardware_detection_stats(db)
    finally:
        db.close()


@router.websocket("/hardware-detection")
async def hardware_detection_websocket(
    websocket: WebSocket,
    locations: Optional[str] = Query(None, description="Comma-separated list of locations to subscribe to"),
    user_id: Optional[int] = Query(None, description="User ID for user-specific updates"),
):
    """
    WebSocket endpoint for real-time hardware detection updates

    Query Parameters:
    - locations: Comma-separated list of locations to subscribe to (e.g., "greenhouse_a,greenhouse_b")
    - user_id: User ID for user-specific updates

    Message Types Sent:
    - connection_established: Sent when connection is established
    - new_detection: New hardware detection created
    - detection_validated: Detection validation status changed
    - bulk_detections_created: Multiple detections created at once
    - detection_processed: Detection result processed for hardware
    - location_status_changed: Location status updated
    - inventory_updated: Location inventory updated
    - hydro_device_matched: Detection matched with hydro device
    - stats_updated: Overall statistics updated
    - ping: Keep-alive ping
    - error: Error message

    Message Types Received:
    - subscribe_location: Subscribe to a location
    - unsubscribe_location: Unsubscribe from a location
    - get_location_status: Get current status for a location
    - get_stats: Get current statistics
    - pong: Response to ping

    NOTE: This handler intentionally does NOT take `db: Session = Depends(get_db)`.
    A websocket connection can live far longer than an HTTP request, and a
    dependency-injected session would be checked out of the pool for the
    entire time the socket is open, not just while a query runs. Instead,
    each place below that needs the DB opens its own short-lived
    SessionLocal() via the helpers above (or inline), and closes it
    immediately after use.
    """

    # Accept the WebSocket connection before doing anything else
    try:
        await websocket.accept()
    except Exception as e:
        logger.error(f"Failed to accept WebSocket connection: {e}")
        return

    # Generate unique connection ID
    connection_id = str(uuid.uuid4())

    # Parse locations
    location_list = []
    if locations:
        location_list = [loc.strip() for loc in locations.split(",") if loc.strip()]

    try:
        # Establish connection
        success = await detection_ws_manager.connect(
            websocket, connection_id, location_list, user_id
        )

        if not success:
            try:
                await websocket.close(code=1000, reason="Failed to establish connection")
            except Exception as close_error:
                logger.error(f"Error closing WebSocket after failed connection: {close_error}")
            return

        # Send initial data if locations are specified
        if location_list:
            for location in location_list:
                try:
                    # Send current location status
                    status = _get_location_status_safely(location)
                    await detection_ws_manager.send_to_connection(connection_id, {
                        "type": "initial_location_status",
                        "location": location,
                        "data": status.dict() if hasattr(status, 'dict') else status,
                        "timestamp": None
                    })
                except Exception as e:
                    logger.warning(f"Could not send initial status for location {location}: {e}")

        # Listen for messages
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                message = json.loads(data)

                message_type = message.get("type")

                if message_type == "subscribe_location":
                    location = message.get("location")
                    if location:
                        await detection_ws_manager.subscribe_to_location(
                            connection_id, location
                        )

                        # Send current location status
                        try:
                            status = _get_location_status_safely(location)
                            await detection_ws_manager.send_to_connection(connection_id, {
                                "type": "location_status",
                                "location": location,
                                "data": status.dict() if hasattr(status, 'dict') else status,
                                "timestamp": None
                            })
                        except Exception as e:
                            logger.warning(f"Could not send status for location {location}: {e}")

                elif message_type == "unsubscribe_location":
                    location = message.get("location")
                    if location:
                        await detection_ws_manager.unsubscribe_from_location(
                            connection_id, location
                        )

                elif message_type == "get_location_status":
                    location = message.get("location")
                    if location:
                        try:
                            status = _get_location_status_safely(location)
                            await detection_ws_manager.send_to_connection(connection_id, {
                                "type": "location_status",
                                "location": location,
                                "data": status.dict() if hasattr(status, 'dict') else status,
                                "timestamp": None
                            })
                        except Exception as e:
                            # Only send error if connection is still active
                            if connection_id in detection_ws_manager.active_connections:
                                await detection_ws_manager.send_to_connection(connection_id, {
                                    "type": "error",
                                    "message": f"Could not get status for location {location}: {str(e)}",
                                    "timestamp": None
                                })

                elif message_type == "get_stats":
                    try:
                        stats = _get_hardware_detection_stats_safely()
                        await detection_ws_manager.send_to_connection(connection_id, {
                            "type": "stats",
                            "data": stats.dict() if hasattr(stats, 'dict') else stats,
                            "timestamp": None
                        })
                    except Exception as e:
                        # Only send error if connection is still active
                        if connection_id in detection_ws_manager.active_connections:
                            await detection_ws_manager.send_to_connection(connection_id, {
                                "type": "error",
                                "message": f"Could not get stats: {str(e)}",
                                "timestamp": None
                            })

                elif message_type == "pong":
                    # Client responded to ping
                    logger.debug(f"Received pong from connection {connection_id}")

                else:
                    # Only send error if connection is still active
                    if connection_id in detection_ws_manager.active_connections:
                        await detection_ws_manager.send_to_connection(connection_id, {
                            "type": "error",
                            "message": f"Unknown message type: {message_type}",
                            "timestamp": None
                        })

            except json.JSONDecodeError:
                # Only send error if connection is still active
                if connection_id in detection_ws_manager.active_connections:
                    await detection_ws_manager.send_to_connection(connection_id, {
                        "type": "error",
                        "message": "Invalid JSON format",
                        "timestamp": None
                    })
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}")
                # Only try to send error if connection is still active
                if connection_id in detection_ws_manager.active_connections:
                    try:
                        await detection_ws_manager.send_to_connection(connection_id, {
                            "type": "error",
                            "message": f"Server error: {str(e)}",
                            "timestamp": None
                        })
                    except Exception as send_error:
                        logger.error(f"Failed to send error message to WebSocket {connection_id}: {send_error}")
                        break  # Exit the loop if we can't send messages
                else:
                    # Connection is no longer active, exit the loop
                    logger.warning(f"Connection {connection_id} is no longer active, exiting message loop")
                    break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {connection_id}")
    except Exception as e:
        logger.error(f"WebSocket error for connection {connection_id}: {e}")
    finally:
        await detection_ws_manager.disconnect(connection_id)


@router.get("/connections/stats")
async def get_websocket_stats():
    """Get statistics about current WebSocket connections"""
    return detection_ws_manager.get_connection_stats()


@router.post("/test-broadcast")
async def test_broadcast(
    location: str,
    message: str = "Test message",
    db: Session = Depends(get_db)
):
    """Test endpoint to broadcast a message to a specific location.

    NOTE: this is a normal HTTP route, not a websocket, so `Depends(get_db)`
    is fine here — FastAPI closes it automatically once the response is
    sent.
    """
    from .events import hardware_detection_broadcaster

    test_data = {
        "test": True,
        "message": message,
        "location": location
    }

    await hardware_detection_broadcaster.broadcast_custom_event(
        "test_broadcast", test_data, location, message=f"Test broadcast to {location}"
    )

    return {"message": f"Test broadcast sent to location: {location}"}


@router.post("/ping-all")
async def ping_all_connections():
    """Send ping to all WebSocket connections"""
    await detection_ws_manager.ping_connections()
    return {"message": "Ping sent to all connections"}