# Hydroponic System Module Documentation

## Overview

The **Hydro System Module** manages ESP32-based hydroponic devices and their actuators (pumps, lights, fans, valves, water sensors). It provides device CRUD operations, actuator control, sensor data collection, and automation rules based on environmental thresholds.

## Architecture

```
app/hydro_system/
├── models/              # SQLAlchemy ORM models
│   ├── device.py        # HydroDevice (ESP32 mainboard)
│   ├── actuator.py      # HydroActuator (pump, light, fan, valve, water_pump)
│   └── sensor_data.py   # SensorData (temperature, humidity, moisture, water level)
├── schemas/             # Pydantic validation schemas
│   ├── device.py        # HydroDeviceCreate, HydroDeviceUpdate, HydroDeviceOut
│   └── actuator.py      # HydroActuatorCreate, HydroActuatorUpdate, HydroActuatorOut
├── controllers/         # Business logic
│   ├── device_controller.py        # Device CRUD + control logic
│   ├── actuator_controller.py      # Actuator state management
│   └── system_controller.py        # System status + automation
├── services/            # Data access layer
│   ├── device_service.py           # Database queries for devices
│   ├── actuator_service.py         # Database queries for actuators
│   └── sensor_data_service.py      # Database queries for sensor readings
├── routes/              # API endpoints
│   ├── device_router.py            # Device CRUD + location control
│   ├── actuator_router.py          # Actuator control endpoints
│   ├── sensor_router.py            # Sensor data endpoints
│   └── system_router.py            # System status endpoints
├── config.py            # Configuration (device IDs, thresholds, actuator types)
├── rules_engine.py      # Automation rules for actuator control
├── scheduler.py         # Background sensor collection job
├── sensors.py           # Sensor reading implementations
└── state_manager.py     # In-memory state tracking
```

## Database Models

### HydroDevice (ESP32 Mainboard)

**Table:** `devices_hydro`

Represents an ESP32 microcontroller that controls hydroponic equipment.

| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `name` | String | Device name (e.g., "Greenhouse Pump Controller") |
| `device_id` | String (Unique) | External device identifier (MAC address, serial number, or UUID) |
| `user_id` | Integer (FK) | User who owns the device |
| `client_id` | String | Multi-tenant client identifier |
| `external_id` | String (Unique, Optional) | Alternative external identifier |
| `location` | String (Optional) | Physical location (e.g., "Greenhouse A", "Farm Building 2") |
| `type` | String (Optional) | Device type (typically "controller") |
| `is_active` | Boolean | Whether device is enabled for hardware communication |
| `thresholds` | JSON (Optional) | Per-device automation thresholds (overrides global config) |
| `actuators` | Relationship | One-to-many relationship to HydroActuator |
| `created_at` | DateTime | Timestamp when device was created |
| `updated_at` | DateTime | Timestamp of last update |

**Example:**
```json
{
  "id": 1,
  "name": "Greenhouse A Controller",
  "device_id": "esp32-dev-001",
  "user_id": 5,
  "client_id": "client_001",
  "location": "Greenhouse A",
  "type": "controller",
  "is_active": true,
  "thresholds": {
    "moisture_min": 35,
    "temperature_max": 26
  }
}
```

### HydroActuator (Physical Equipment)

**Table:** `hydro_actuators`

Represents individual hardware components (pumps, lights, fans, valves, water sensors) connected to a device.

| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `type` | String | Actuator type: `pump`, `light`, `fan`, `water_pump`, `valve` |
| `name` | String (Optional) | Human-readable name (e.g., "Pump 1", "Grow Light A") |
| `pin` | String (Optional) | GPIO pin identifier (e.g., "D1", "GPIO23") |
| `port` | Integer | GPIO pin number on ESP32 |
| `is_active` | Boolean | Whether actuator is enabled for control |
| `default_state` | Boolean | Initial/default state (ON=true, OFF=false) |
| `device_id` | Integer (FK) | Parent device |
| `sensor_key` | String (Optional) | Linked sensor type (e.g., "temperature", "humidity") |
| `created_at` | DateTime | Creation timestamp |
| `updated_at` | DateTime | Last update timestamp |

**Supported Types:**
- `pump` - General pump control
- `light` - Grow lights
- `fan` - Exhaust/circulation fans
- `water_pump` - Water circulation/refill
- `valve` - Water valve control
- `nutrient_pump` - Nutrient dosing pump

**Example:**
```json
{
  "id": 10,
  "type": "pump",
  "name": "Main Water Pump",
  "pin": "D1",
  "port": 1,
  "is_active": true,
  "default_state": false,
  "device_id": 1,
  "sensor_key": "water_level"
}
```

### SensorData

**Table:** `sensor_data`

Historical readings from sensors (temperature, humidity, moisture, water level).

| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `device_id` | Integer (FK) | Parent device |
| `temperature` | Float | Temperature reading (°C) |
| `humidity` | Float | Humidity reading (%) |
| `light` | Float | Light intensity (lux) |
| `moisture` | Float | Soil moisture (%) |
| `water_level` | Float | Water level (%) |
| `ec` | Float | Electrical Conductivity (mS/cm) |
| `ppm` | Float | Parts Per Million (PPM) |
| `created_at` | DateTime | When reading was taken |

## API Endpoints

### Device Management

#### List Devices

```http
GET /hydro/devices?skip=0&limit=100&user_id=5&client_id=client_001
```

**Query Parameters:**
- `skip` (int, default=0): Pagination offset
- `limit` (int, default=100): Items per page
- `user_id` (int, optional): Filter by user
- `client_id` (string, optional): Filter by client

**Response:** `List[HydroDeviceOut]`

**Behavior:**
- SuperAdmin sees all devices
- Regular users see only their client's devices
- If no filters provided, returns current user's client devices

**Example:**
```json
[
  {
    "id": 1,
    "name": "Greenhouse A Controller",
    "device_id": "esp32-dev-001",
    "location": "Greenhouse A",
    "is_active": true,
    "user_id": 5,
    "created_at": "2025-01-15T10:30:00Z",
    "updated_at": "2025-01-15T14:22:00Z"
  }
]
```

#### Get Device by ID

```http
GET /hydro/devices/{device_id}
```

**Path Parameters:**
- `device_id` (int, required): Device internal ID

**Response:** `HydroDeviceOut`

#### Create Device

```http
POST /hydro/devices
Content-Type: application/json

{
  "name": "Greenhouse B Controller",
  "device_id": "esp32-dev-002",
  "location": "Greenhouse B",
  "type": "controller",
  "is_active": true
}
```

**Authenticated:** Required (user_id and client_id auto-assigned from JWT)

**Request Body:**
- `name` (string, required): Device name
- `device_id` (string, required): External device identifier (must be unique)
- `location` (string, optional): Physical location
- `type` (string, optional): Device type
- `is_active` (boolean, optional, default=true)
- `external_id` (string, optional): Alternative identifier
- `thresholds` (object, optional): Automation thresholds override

**Response:** `HydroDeviceOut` (201 Created)

**Behavior (Mock Mode):**
- Default actuators are automatically created based on `config.DEFAULT_ACTUATORS`

#### Update Device

```http
PUT /hydro/devices/{device_id}
Content-Type: application/json

{
  "name": "Updated Greenhouse A",
  "location": "Greenhouse A Updated",
  "thresholds": {
    "moisture_min": 40,
    "temperature_max": 25
  }
}
```

**Path Parameters:**
- `device_id` (int, required)

**Request Body:** `HydroDeviceUpdate` (all fields optional)

**Response:** `HydroDeviceOut`

#### Delete Device

```http
DELETE /hydro/devices/{device_id}
```

**Path Parameters:**
- `device_id` (int, required)

**Response:** `{"detail": "Device deleted successfully"}`

#### Activate Device

```http
POST /hydro/devices/{device_id}/activate
```

**Path Parameters:**
- `device_id` (int, required)

**Response:** `HydroDeviceOut`

**Behavior:**
- Sets `is_active = true`
- Enables hardware heartbeat and communication
- Activates automation rules for this device

#### Deactivate Device

```http
POST /hydro/devices/{device_id}/deactivate
```

**Path Parameters:**
- `device_id` (int, required)

**Response:** `HydroDeviceOut`

**Behavior:**
- Sets `is_active = false`
- Disables hardware communication
- Pauses automation rules

### Device Location Control

#### Control Devices by Location

```http
POST /hydro/devices/location/{location}/control?on=true
```

**Path Parameters:**
- `location` (string, required): Physical location (e.g., "Greenhouse A")

**Query Parameters:**
- `on` (boolean, required): true=turn ON, false=turn OFF

**Response:**
```json
{
  "location": "Greenhouse A",
  "state": "ON",
  "devices_controlled": 1,
  "details": [
    {
      "device_id": 1,
      "device_name": "Greenhouse A Controller",
      "location": "Greenhouse A",
      "actuators_controlled": [
        {
          "actuator_id": 10,
          "name": "Main Water Pump",
          "type": "pump",
          "state": "ON"
        },
        {
          "actuator_id": 11,
          "name": "Grow Light A",
          "type": "light",
          "state": "ON"
        }
      ]
    }
  ]
}
```

**Behavior:**
1. Queries all devices matching the specified `location`
2. For each device, controls **all actuators** (turns them ON or OFF)
3. Uses `control_actuator_by_id()` to toggle each actuator
4. Logs actuator state changes
5. Returns detailed control results per device

**Error Responses:**
- `404 Not Found`: No devices at specified location
- `500 Internal Server Error`: Actuator control failure

**Example Requests:**
```bash
# Turn ON all devices in Greenhouse A
curl -X POST "http://localhost:8000/hydro/devices/location/Greenhouse%20A/control?on=true"

# Turn OFF all devices in Farm Building 2
curl -X POST "http://localhost:8000/hydro/devices/location/Farm%20Building%202/control?on=false"
```

### Actuator Control

#### Get Actuators by Device

```http
GET /hydro/actuators/device/{device_id}
```

**Path Parameters:**
- `device_id` (int, required): Device internal ID

**Response:** `List[HydroActuatorOut]`

#### Create Actuator

```http
POST /hydro/actuators
Content-Type: application/json

{
  "name": "Pump A",
  "type": "pump",
  "port": 1,
  "pin": "D1",
  "device_id": 1,
  "is_active": true,
  "default_state": false,
  "sensor_key": "water_level"
}
```

**Request Body:** `HydroActuatorCreate`

**Response:** `HydroActuatorOut` (201 Created)

#### Update Actuator

```http
PUT /hydro/actuators/{actuator_id}
```

**Path Parameters:**
- `actuator_id` (int, required)

**Request Body:** `HydroActuatorUpdate` (all fields optional)

**Response:** `HydroActuatorOut`

### Sensor Data

#### Get Sensor Data

```http
GET /hydro/sensors?device_id=1&limit=100&skip=0
```

**Query Parameters:**
- `device_id` (int, optional): Filter by device
- `limit` (int, default=100): Items per page
- `skip` (int, default=0): Pagination offset

**Response:** `List[SensorDataOut]`

#### Get Latest Sensor Data

```http
GET /hydro/sensors/latest?device_id=1
```

**Response:** `SensorDataOut`

### System Status

#### Get System Status

```http
GET /hydro/status?device_id=1
```

**Query Parameters:**
- `device_id` (int, optional): If not provided, uses first active device

**Response:**
```json
{
  "device_id": 1,
  "device_name": "Greenhouse A Controller",
  "is_active": true,
  "last_reading": {
    "temperature": 22.5,
    "humidity": 65,
    "moisture": 45,
    "water_level": 75,
    "ec": 1.8,
    "ppm": 900
  },
  "actuator_states": {
    "pump_1_1": false,
    "light_1_2": true,
    "fan_1_3": false
  },
  "automation_active": true,
  "last_automation_run": "2025-01-15T14:20:00Z"
}
```

## Configuration

### File: `app/hydro_system/config.py`

#### Device IDs
```python
DEVICE_IDS = [
    "esp32-dev-001",
    "esp32-dev-002",
    "esp32-dev-003",
]
```

#### Default Thresholds
```python
DEFAULT_THRESHOLDS = {
    "moisture_min": 30,        # % - soil moisture
    "light_min": 300,          # lux - light intensity
    "temperature_max": 28,     # °C - max temperature
    "water_level_min": 20,     # % - min water level
    "water_level_critical": 10, # % - emergency alert level
    "ec_min": 1.2,             # mS/cm - min EC
    "ec_max": 2.5,             # mS/cm - max EC
    "ppm_min": 600,            # ppm - min PPM
    "ppm_max": 1000            # ppm - max PPM
}
```

#### Default Actuators (Mock Mode)
```python
DEFAULT_ACTUATORS = [
    {"type": "pump", "name": "Pump A", "port": 1, ...},
    {"type": "light", "name": "Grow Light A", "port": 2, ...},
    ...
]
```
Created automatically when device is created in mock mode.

#### Actuator Types
```python
ACTUATOR_TYPES = {
    "pump": {"emoji_on": "✅", "label": "Pump"},
    "light": {"emoji_on": "💡", "label": "Light"},
    "fan": {"emoji_on": "🌪️", "label": "Fan"},
    "water_pump": {"emoji_on": "💧", "label": "Water Pump"},
    "valve": {"emoji_on": "🔓", "label": "Valve"},
    "nutrient_pump": {"emoji_on": "🧪", "label": "Nutrient Pump"},
}
```

## Service Layer

### HydroDeviceService

**Location:** `app/hydro_system/services/device_service.py`

**Key Methods:**

| Method | Signature | Purpose |
|--------|-----------|---------|
| `create_device()` | `(db, device_in: HydroDeviceCreate) -> HydroDevice` | Create new device, auto-create default actuators |
| `get_device()` | `(db, device_id: int) -> HydroDevice` | Fetch by internal ID |
| `get_device_by_external_id()` | `(db, external_id: str) -> HydroDevice` | Fetch by device_id |
| `get_devices_by_location()` | `(db, location: str) -> List[HydroDevice]` | **NEW** - Fetch all devices at a location |
| `get_devices_by_user()` | `(db, user_id: int) -> List[HydroDevice]` | Fetch user's devices |
| `get_devices_by_client()` | `(db, client_id: str) -> List[HydroDevice]` | Fetch client's devices |
| `get_first_active_device()` | `(db) -> HydroDevice` | Get the first active device for fallback |
| `update_device()` | `(db, device: HydroDevice, updates) -> HydroDevice` | Update device fields |
| `delete_device()` | `(db, device: HydroDevice) -> None` | Delete device and cascading actuators |
| `set_device_active()` | `(db, device_id: int, active: bool) -> HydroDevice` | Toggle device active status |
| `control_devices_by_location()` | `(db, location: str, on: bool) -> dict` | **NEW** - Control all devices at location |

### HydroActuatorService

**Location:** `app/hydro_system/services/actuator_service.py`

| Method | Signature | Purpose |
|--------|-----------|---------|
| `create_actuator()` | `(db, actuator_in) -> HydroActuator` | Create actuator |
| `get_actuator()` | `(db, actuator_id: int) -> HydroActuator` | Fetch by ID |
| `get_actuators_by_device()` | `(db, device_id: int) -> List[HydroActuator]` | Fetch device's actuators |
| `get_actuators_by_device_and_type()` | `(db, device_id, type) -> List[HydroActuator]` | Filter by device and type |
| `update_actuator()` | `(db, actuator_id, updates) -> HydroActuator` | Update actuator |
| `delete_actuator()` | `(db, actuator_id: int) -> bool` | Delete actuator |
| `update_actuators_by_type()` | `(db, device_id, type, value) -> List[HydroActuator]` | Bulk toggle by type |

## Controllers

### device_controller.py

Acts as a facade between routes and services. Adds error handling and logging.

**Key Functions:**

```python
# Device CRUD
create_device(db, device_in)
get_device(db, device_id)
get_devices_by_user(db, user_id)
get_devices_by_client(db, client_id, skip, limit)
get_all_devices(db, skip, limit)
update_device(db, device_id, updates)
delete_device(db, device_id)

# Device Control
activate_device(db, device_id)
deactivate_device(db, device_id)
control_devices_by_location(db, location, on)  # NEW
```

### actuator_controller.py

Manages actuator state and hardware control.

**Key Functions:**

```python
# Actuator Control
control_actuator(db, device_type, on, device_id)
control_actuator_by_id(db, actuator_id, on)

# Automation
handle_automation(db, sensor_data, device_id)
log_device_action(name, device_type, state, ...)
```

## Usage Examples

### Create a Device

```bash
curl -X POST "http://localhost:8000/hydro/devices" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Greenhouse A Controller",
    "device_id": "esp32-dev-001",
    "location": "Greenhouse A",
    "type": "controller"
  }'
```

### Control All Devices at a Location

```bash
# Turn ON
curl -X POST "http://localhost:8000/hydro/devices/location/Greenhouse%20A/control?on=true" \
  -H "Authorization: Bearer <token>"

# Turn OFF
curl -X POST "http://localhost:8000/hydro/devices/location/Greenhouse%20A/control?on=false" \
  -H "Authorization: Bearer <token>"
```

### Get Devices by Location (Service Usage)

```python
from app.hydro_system.services.device_service import hydro_device_service

devices = hydro_device_service.get_devices_by_location(db, "Greenhouse A")
# Returns: List[HydroDevice]
```

### Update Device Thresholds

```bash
curl -X PUT "http://localhost:8000/hydro/devices/1" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "thresholds": {
      "moisture_min": 35,
      "temperature_max": 26,
      "water_level_min": 25
    }
  }'
```

## Data Flow

### Device Location Control Flow

```
POST /hydro/devices/location/{location}/control?on=true
  ↓
device_router.control_devices_by_location()
  ↓
device_controller.control_devices_by_location()
  ↓
device_service.get_devices_by_location(db, location)
  ↓ (for each device)
device_service.actuator_service.control_actuator_by_id()
  ↓
state_manager.set_state()
  ↓ (send to ESP32 hardware via MQTT/Serial/API)
```

### Automation Flow

```
Sensor Collection Job (60s interval)
  ↓
sensors.read_sensor_data()
  ↓
device_controller.handle_automation()
  ↓
rules_engine.check_rules(sensor_data, thresholds)
  ↓
actuator_controller.control_actuator_by_id()  (if rule triggered)
  ↓
state_manager.set_state()
  ↓
log_actuator_action()
```

## Background Jobs

### Sensor Collection Job

**File:** `app/hydro_system/scheduler.py`

- **Frequency:** Every 60 seconds
- **Trigger:** Reads all sensors on active devices
- **Actions:**
  1. Collects sensor data (temperature, humidity, moisture, water level, ec, ppm)
  2. Persists readings to `SensorData` table
  3. Evaluates automation rules based on thresholds
  4. Controls actuators if conditions are met
  5. Generates alerts if critical levels reached

**Registration:**
```python
# main.py
from app.hydro_system.scheduler import start_sensor_job
start_sensor_job()
```

## State Management

### State Manager

**File:** `app/hydro_system/state_manager.py`

In-memory storage for actuator states (ON/OFF).

```python
from app.hydro_system.state_manager import set_state, get_state

# Set state
set_state("pump_1_1", True)  # Turn pump ON

# Get state
is_on = get_state("pump_1_1")
```

**State Key Format:** `{actuator_type}_{device_id}_{port}`

Example: `pump_1_1` = pump on device 1, port 1

## Troubleshooting

### Device Not Responding

1. Check device `is_active` status
2. Verify `device_id` matches ESP32 configuration
3. Check network connectivity
4. Review scheduler logs for sensor collection errors

### Automation Not Triggering

1. Verify `is_active = true` on device
2. Check thresholds in device config or database
3. Review `rules_engine.py` logic
4. Check sensor data is being collected (look at `SensorData` table)

### No Devices at Location

1. Verify device `location` field is set correctly
2. Ensure devices are in the correct client
3. Check user permissions (SuperAdmin can see all)

## Security Considerations

1. **Authentication:** All endpoints require valid JWT token
2. **Authorization:** Users see only their client's devices (SuperAdmin sees all)
3. **Input Validation:** Pydantic schemas validate all inputs
4. **SQL Injection:** SQLAlchemy ORM prevents SQL injection
5. **Device ID Uniqueness:** `device_id` is unique at database level

## Future Enhancements

- [ ] WebSocket real-time actuator state updates
- [ ] Device grouping/zones (multiple devices per location)
- [ ] Advanced scheduling (time-based rules)
- [ ] Historical analytics dashboard
- [ ] Hardware firmware update management
- [ ] MQTT integration for remote devices
- [ ] Alerts/notifications (email, SMS)
- [ ] Per-actuator control at location level

## Related Files

- **Models:** `app/hydro_system/models/`
- **Schemas:** `app/hydro_system/schemas/`
- **Routes:** `app/hydro_system/routes/system_router.py` (main entry point)
- **Scheduler:** `app/hydro_system/scheduler.py`
- **Configuration:** `app/hydro_system/config.py`
- **Main App:** `main.py` (register scheduler and routers)
