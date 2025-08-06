# Hardware Detection WebSocket Real-time Updates

This module provides real-time WebSocket communication for hardware detection events, allowing frontend applications to receive instant updates when hardware is detected, validated, or when location status changes.

## Features

- **Real-time Updates**: Instant notifications for hardware detection events
- **Location-based Subscriptions**: Subscribe to specific locations for targeted updates
- **User-specific Updates**: Support for user-specific notifications
- **Event Broadcasting**: Multiple event types for different scenarios
- **Connection Management**: Robust connection handling with automatic cleanup
- **Background Tasks**: Periodic updates and connection maintenance

## WebSocket Endpoint

```
ws://localhost:8000/hardware-detection/ws/hardware-detection
```

### Query Parameters

- `locations` (optional): Comma-separated list of locations to subscribe to
- `user_id` (optional): User ID for user-specific updates

### Example Connection URLs

```javascript
// Subscribe to specific locations
ws://localhost:8000/hardware-detection/ws/hardware-detection?locations=greenhouse_a,greenhouse_b

// Subscribe with user ID
ws://localhost:8000/hardware-detection/ws/hardware-detection?user_id=123

// Subscribe to locations and user
ws://localhost:8000/hardware-detection/ws/hardware-detection?locations=greenhouse_a&user_id=123
```

## Event Types

### Outgoing Events (Server → Client)

| Event Type | Description | Trigger |
|------------|-------------|---------|
| `connection_established` | Sent when connection is established | WebSocket connection |
| `new_detection` | New hardware detection created | POST `/hardware-detection/` |
| `detection_validated` | Detection validation status changed | PUT `/hardware-detection/{id}/validate` |
| `bulk_detections_created` | Multiple detections created | POST `/hardware-detection/bulk` |
| `detection_processed` | Detection result processed | POST `/hardware-detection/process-detection/{id}` |
| `location_status_changed` | Location status updated | Periodic updates |
| `inventory_updated` | Location inventory updated | POST `/hardware-detection/inventory` |
| `hydro_device_matched` | Detection matched with hydro device | Service integration |
| `stats_updated` | Overall statistics updated | Periodic updates |
| `ping` | Keep-alive ping | Every 30 seconds |
| `error` | Error message | Various error conditions |

### Incoming Messages (Client → Server)

| Message Type | Description | Parameters |
|--------------|-------------|------------|
| `subscribe_location` | Subscribe to location updates | `location`: string |
| `unsubscribe_location` | Unsubscribe from location | `location`: string |
| `get_location_status` | Get current location status | `location`: string |
| `get_stats` | Get current statistics | None |
| `pong` | Response to ping | None |

## Message Format

### Outgoing Message Structure

```json
{
  "type": "event_type",
  "data": { /* event-specific data */ },
  "location": "location_name",  // if applicable
  "timestamp": "2024-01-01T12:00:00Z",
  "message": "Human-readable description"
}
```

### Incoming Message Structure

```json
{
  "type": "message_type",
  "location": "location_name",  // if applicable
  /* additional parameters based on message type */
}
```

## Usage Examples

### JavaScript Client

```javascript
// Connect to WebSocket
const ws = new WebSocket('ws://localhost:8000/hardware-detection/ws/hardware-detection?locations=greenhouse_a');

ws.onopen = function(event) {
    console.log('Connected to hardware detection WebSocket');
};

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    
    switch(data.type) {
        case 'new_detection':
            console.log('New hardware detected:', data.data);
            updateUI(data);
            break;
            
        case 'detection_validated':
            console.log('Detection validated:', data.data);
            updateValidationStatus(data);
            break;
            
        case 'location_status_changed':
            console.log('Location status changed:', data.data);
            updateLocationStatus(data);
            break;
            
        default:
            console.log('Received event:', data);
    }
};

// Subscribe to additional location
ws.send(JSON.stringify({
    type: 'subscribe_location',
    location: 'greenhouse_b'
}));

// Get current location status
ws.send(JSON.stringify({
    type: 'get_location_status',
    location: 'greenhouse_a'
}));
```

### React Hook Example

```javascript
import { useState, useEffect, useRef } from 'react';

function useHardwareDetectionWebSocket(locations = [], userId = null) {
    const [isConnected, setIsConnected] = useState(false);
    const [lastMessage, setLastMessage] = useState(null);
    const [detections, setDetections] = useState([]);
    const ws = useRef(null);

    useEffect(() => {
        const params = new URLSearchParams();
        if (locations.length > 0) params.append('locations', locations.join(','));
        if (userId) params.append('user_id', userId);
        
        const url = `ws://localhost:8000/hardware-detection/ws/hardware-detection?${params}`;
        ws.current = new WebSocket(url);

        ws.current.onopen = () => setIsConnected(true);
        ws.current.onclose = () => setIsConnected(false);
        
        ws.current.onmessage = (event) => {
            const data = JSON.parse(event.data);
            setLastMessage(data);
            
            if (data.type === 'new_detection') {
                setDetections(prev => [...prev, data.data]);
            }
        };

        return () => {
            ws.current?.close();
        };
    }, [locations, userId]);

    const subscribeToLocation = (location) => {
        if (ws.current?.readyState === WebSocket.OPEN) {
            ws.current.send(JSON.stringify({
                type: 'subscribe_location',
                location
            }));
        }
    };

    return {
        isConnected,
        lastMessage,
        detections,
        subscribeToLocation
    };
}
```

## Testing

### Using the Test Client

1. Open `test_client.html` in your browser
2. Ensure your FastAPI server is running
3. Configure the WebSocket URL and parameters
4. Click "Connect" to establish connection
5. Use the controls to test different message types

### Using curl for HTTP endpoints

```bash
# Test broadcast endpoint
curl -X POST "http://localhost:8000/hardware-detection/ws/test-broadcast?location=greenhouse_a&message=Hello"

# Get WebSocket connection stats
curl "http://localhost:8000/hardware-detection/ws/connections/stats"

# Ping all connections
curl -X POST "http://localhost:8000/hardware-detection/ws/ping-all"
```

## Integration with Hydro System

The WebSocket system automatically integrates with your hydro system:

1. **Device Matching**: When hardware detections match hydro devices, `hydro_device_matched` events are broadcast
2. **Location Sync**: Inventory sync operations trigger `inventory_updated` events
3. **Status Updates**: Location status changes are broadcast to subscribed clients

## Background Tasks

The system runs several background tasks:

- **Periodic Ping**: Keeps connections alive (every 30 seconds)
- **Stats Updates**: Broadcasts updated statistics (every 5 minutes)
- **Location Status**: Updates location status for subscribed locations (every 10 minutes)

## Error Handling

The WebSocket system includes robust error handling:

- Automatic connection cleanup on disconnect
- Error messages sent to clients for invalid requests
- Graceful handling of malformed JSON
- Connection state validation before sending messages

## Performance Considerations

- Connections are automatically cleaned up when clients disconnect
- Background tasks only run when there are active connections
- Location-based broadcasting reduces unnecessary network traffic
- Message serialization uses efficient JSON encoding

## Security Notes

- Consider implementing authentication for WebSocket connections
- Validate user permissions for location subscriptions
- Rate limiting may be needed for high-traffic scenarios
- Use WSS (WebSocket Secure) in production environments