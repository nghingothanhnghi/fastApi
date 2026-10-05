# Bida (Billiard) Management Module

Production-oriented specification for a billiard table management system integrated with an existing FastAPI backend, Product module, Payment module, User/Auth module, React POS, and one central ESP32 controller managing up to 10 billiard tables.

---

## 1. Overview

The Bida module manages:

- Multiple billiard tables
- Table availability and reservation
- Table playing sessions
- Session duration and table billing
- Multiple games inside one session
- Player A / Player B scores
- Physical electronic scoreboards
- Food and drink orders
- Product price snapshots
- Billiard packages with included products
- Payments through the existing Payment module
- Usage and revenue reports
- One central ESP32 controller for all tables
- RS485 communication with table electronics
- Offline/manual operation when Wi-Fi is unavailable
- Persistent offline event queue
- Automatic synchronization when connectivity returns
- React POS real-time updates

The central design principle is:

> The ESP32 controls physical interaction and local display. FastAPI is the authoritative source for business state, billing, products, and payments.

---

# 2. System Architecture

```text
                         React POS / Admin
                                |
                                | REST / WebSocket
                                v
                         +--------------+
                         |    FastAPI   |
                         +------+-------+
                                |
             +------------------+------------------+
             |                  |                  |
             v                  v                  v
        User/Auth           Products           Payments
             |                  |                  |
             +------------------+------------------+
                                |
                                v
                         +--------------+
                         |   BILLIARD   |
                         |    MODULE    |
                         +------+-------+
                                |
                                | REST / sync
                                v
                     +-----------------------+
                     | CENTRAL ESP32         |
                     |                       |
                     | Local State           |
                     | Event Queue           |
                     | Sync Manager          |
                     | Timer Engine          |
                     | RS485 Manager         |
                     +----------+------------+
                                |
                              RS485
                                |
             +------------------+------------------+
             |                  |                  |
             v                  v                  v
          Table 01           Table 02          Table 03
             |                  |                  |
          Display            Display           Display
          Buttons            Buttons           Buttons
             |                  |                  |
             +------------------+------------------+
                                |
                              ... T10
```

Only **one central ESP32** is required.

There must NOT be one ESP32 per table.

---

# 3. Main Responsibilities

## FastAPI owns

- Table records
- Table status
- Session lifecycle
- Official start/end timestamps
- Billing
- Pricing rules
- Packages
- Products
- Product prices
- Product inventory integration
- Payment
- Game history
- Event processing
- Event idempotency
- Reports
- User permissions
- Device registration
- Server-side state

## Central ESP32 owns

- Physical button input
- Physical display output
- Local score state
- Local countdown display
- RS485 communication
- Offline operation
- Persistent local event queue
- Temporary local session/game identifiers
- Synchronization with FastAPI
- Reboot recovery

## ESP32 must NOT be authoritative for

- Final billing
- Payment status
- Product price
- Grand total
- Official historical revenue
- User permissions

---

# 4. Recommended Backend Structure

```text
app/
    └── billiard/
        ├── models/
        │   ├── __init__.py
        │   ├── table.py
        │   ├── session.py
        │   ├── session_item.py
        │   ├── game.py
        │   ├── pricing_rule.py
        │   ├── package.py
        │   ├── package_item.py
        │   ├── device.py
        │   └── device_event.py
        │
        ├── schemas/
        │   ├── table.py
        │   ├── session.py
        │   ├── session_item.py
        │   ├── game.py
        │   ├── pricing.py
        │   ├── package.py
        │   ├── device.py
        │   └── event.py
        │
        ├── services/
        │   ├── table_service.py
        │   ├── session_service.py
        │   ├── game_service.py
        │   ├── billing_service.py
        │   ├── package_service.py
        │   ├── device_service.py
        │   └── event_service.py
        │
        ├── controllers/
        │   ├── table_controller.py
        │   ├── session_controller.py
        │   ├── game_controller.py
        │   ├── billing_controller.py
        │   └── device_controller.py
        │
        ├── routes/
        │   ├── table_routes.py
        │   ├── session_routes.py
        │   ├── game_routes.py
        │   ├── package_routes.py
        │   ├── report_routes.py
        │   └── device_routes.py
        │
        ├── jobs/
        │   └── device_monitor.py
        │
        └── constants.py
```

Follow the existing project's architecture rather than duplicating infrastructure.

---

# 5. Database Model

## 5.1 billiard_tables

```text
billiard_tables
----------------
id
name
status
hourly_rate
is_active
created_at
updated_at
```

Statuses:

```text
available
playing
reserved
maintenance
```

Example:

```text
1  B01  available
2  B02  playing
3  B03  available
...
10 B10  reserved
```

The code must not hardcode exactly 10 tables. The database should support any number of tables.

---

# 6. Table Sessions

A `TableSession` represents one customer/table billing period.

```text
table_sessions
----------------
id
table_id

started_at
ended_at
duration_minutes

status

hourly_rate_snapshot
table_fee
total_product_fee
discount
grand_total

created_by
started_by
stopped_by
paid_by

created_at
updated_at
```

Statuses:

```text
active
completed
cancelled
```

Example:

```text
Table 01

Session #1001
09:00 -> 11:15
Duration: 135 minutes
Rate: 100,000/hour
Table fee: 225,000
Products: 85,000
Grand total: 310,000
```

---

# 7. Session vs Game

A session and a game are NOT the same thing.

A customer may play multiple games during one paid table session.

```text
Table 01
|
+-- Session #1001
    |
    +-- Game 1: 09:00 - 09:35
    |   A 10 : B 8
    |
    +-- Game 2: 09:35 - 10:10
    |   A 7 : B 10
    |
    +-- Game 3: 10:10 - 10:45
        A 8 : B 6
```

Starting a new game does NOT stop billing.

---

# 8. table_games

```text
table_games
----------------
id
session_id
game_number
started_at
ended_at

player_a_score
player_b_score

status

created_at
updated_at
```

Statuses:

```text
active
completed
cancelled
```

When `NEW GAME` is pressed:

1. Complete current game
2. Create next game
3. Set both scores to zero
4. Continue the existing table session
5. Do not restart the billing timer

---

# 9. Score Management

Each table supports:

```text
Player A +
Player A -

Player B +
Player B -

Reset Score
New Game
```

Rules:

- Score cannot become negative.
- Every score modification should create an auditable event.
- ESP32 can update the physical display immediately.
- FastAPI must eventually receive and persist the event.
- Duplicate events must not increment the score twice.

Example event:

```json
{
  "event_id": "uuid",
  "device_id": "BILLIARD-CONTROLLER-01",
  "event": "score_change",
  "timestamp": "2026-10-04T15:20:00+07:00",
  "data": {
    "table_id": 4,
    "game_id": 203,
    "player": "A",
    "delta": 1,
    "score_a": 9,
    "score_b": 6
  }
}
```

---

# 10. Electronic Scoreboard

Each physical table has an electronic display and buttons.

Example active display:

```text
+----------------------+
|      TABLE 01        |
|                      |
|       08 : 06        |
|       A     B        |
|                      |
|       01:24:35       |
|                      |
| Start  09:15         |
| End    10:45         |
|                      |
|       GAME 03        |
+----------------------+
```

Idle:

```text
+----------------------+
|      TABLE 01        |
|                      |
|      AVAILABLE       |
|                      |
+----------------------+
```

Offline:

```text
+----------------------+
|      TABLE 01        |
|                      |
|       08 : 06        |
|                      |
|       01:24:35       |
|                      |
|       OFFLINE        |
+----------------------+
```

The display implementation must be abstracted so the business logic does not depend on a particular display library.

---

# 11. Central ESP32

Use exactly one central ESP32.

It manages all 10 tables:

```text
Central ESP32
|
+-- Table 01 state
+-- Table 02 state
+-- Table 03 state
+-- Table 04 state
+-- Table 05 state
+-- Table 06 state
+-- Table 07 state
+-- Table 08 state
+-- Table 09 state
+-- Table 10 state
```

Example local state:

```python
TableState(
    table_id=4,
    status="playing",
    session_id=1004,
    game_id=203,
    game_number=3,
    player_a_score=8,
    player_b_score=6,
    started_at=...,
    ends_at=...,
)
```

---

# 12. ESP32 Firmware Structure

Recommended MicroPython structure:

```text
esp32/
├── main.py
├── config.py
├── secrets.py
├── wifi.py
├── api_client.py
├── billiard_controller.py
├── table_state.py
├── timer_manager.py
├── rs485.py
├── display.py
├── buttons.py
├── event_queue.py
├── sync_manager.py
├── storage.py
├── device.py
└── logger.py
```

Responsibilities:

### `main.py`

Main coordinator.

### `billiard_controller.py`

Controls all 10 table states.

### `table_state.py`

Runtime model for each table.

### `timer_manager.py`

Calculates countdowns from timestamps.

### `rs485.py`

Handles communication with table hardware.

### `buttons.py`

Reads physical input.

### `display.py`

Renders scoreboard state.

### `event_queue.py`

Stores unsynchronized events.

### `sync_manager.py`

Synchronizes events with FastAPI.

### `storage.py`

Persistent local storage.

### `api_client.py`

HTTP communication with FastAPI.

---

# 13. RS485

Use RS485 to connect the central ESP32 to the physical table electronics.

```text
Central ESP32
      |
    RS485
      |
      +-- Address 01 -> Table 01
      +-- Address 02 -> Table 02
      +-- Address 03 -> Table 03
      ...
      +-- Address 10 -> Table 10
```

Each table node needs a unique address.

The protocol should contain:

```text
address
message type
sequence number
payload
CRC/checksum
```

Implement:

- CRC validation
- timeout
- retry
- duplicate detection
- invalid packet handling
- communication status
- table-node offline state

The table nodes do not need to be ESP32s. They may use simpler microcontrollers or suitable IO/display hardware.

---

# 14. Backend Device Model

Create:

```text
billiard_devices
----------------
id
device_id
name
status
firmware_version
last_seen
created_at
updated_at
```

Example:

```text
BILLIARD-CONTROLLER-01
```

This represents the single central ESP32.

Do not create one backend device for every table.

Tables are associated with the central controller through their physical RS485 address/configuration.

---

# 15. Device Events

Create:

```text
device_events
----------------
id
event_id UNIQUE
device_id
table_id
event_type
timestamp
payload
status
created_at
processed_at
```

Possible event types:

```text
heartbeat
button_press
score_change
score_reset
game_start
game_end
new_game
session_start
session_stop
time_extend
table_status
device_error
```

---

# 16. Event Idempotency

Every event must have a unique `event_id`.

Example:

```text
ESP32
 |
 +-- event ABC
 |
 +-- network timeout
 |
 +-- retry event ABC
```

FastAPI must detect that `ABC` was already processed.

The second request returns:

```json
{
  "event_id": "ABC",
  "status": "duplicate"
}
```

It must NOT apply the score change twice.

Use a database unique constraint on `event_id`.

---

# 17. Offline-First Operation

The central ESP32 must continue operating when Wi-Fi or FastAPI is unavailable.

Offline operations:

- Score +/-
- Reset score
- New game
- Start local session
- Stop local session
- Display countdown
- Display start/end time
- Extend/reduce time if the business rules allow it
- Continue all 10 table displays

Do not lock the boards because Wi-Fi is unavailable.

---

# 18. Offline Mode

When disconnected:

```text
Wi-Fi
  X
  |
ESP32
  |
LOCAL MODE
```

The ESP32 continues controlling the physical tables.

Display a connection indicator:

```text
ONLINE
OFFLINE
SYNCING
SYNC ERROR
```

The player should still be able to play and update scores.

---

# 19. Persistent Offline Event Queue

Important events must be stored persistently.

Example:

```text
EVENT QUEUE

001 session_start
002 game_start
003 score_change
004 score_change
005 new_game
006 score_change
007 session_stop
```

Do not remove an event until FastAPI acknowledges it.

Use persistent storage such as LittleFS or another reliable storage mechanism supported by the selected MicroPython firmware.

Do not write the countdown to flash every second.

Persist state transitions, not continuously changing timer values.

---

# 20. Offline Local IDs

When FastAPI is unavailable, the ESP32 may not have server-generated IDs.

Use:

```text
local_session_id
local_game_id
event_id
```

Example:

```text
LOCAL-S-20261004-0001
LOCAL-G-20261004-0001
```

When synchronized:

```text
LOCAL-S-20261004-0001
        |
        v
FastAPI Session #1055
```

and:

```text
LOCAL-G-20261004-0001
        |
        v
FastAPI Game #301
```

Keep the mapping until synchronization is complete.

---

# 21. Offline Session Example

Scenario:

```text
10:00
Wi-Fi disconnected

10:05
Table 03 starts

10:20
Game 1 = 5:3

10:40
New Game

10:45
Game 2 = 7:4

11:30
Session stopped

11:35
Wi-Fi reconnects
```

ESP32 queues:

```text
session_start
game_start
score_change
new_game
score_change
session_stop
```

After reconnect:

```text
ESP32
  |
  +-- send session_start
  +-- send game_start
  +-- send score_change
  +-- send new_game
  +-- send score_change
  +-- send session_stop
  |
  v
FastAPI
```

FastAPI creates the official records.

---

# 22. Synchronization API

Recommended endpoints:

```text
GET  /billiard/controller/state
POST /billiard/controller/events
POST /billiard/controller/sync
```

Batch sync request:

```json
{
  "device_id": "BILLIARD-CONTROLLER-01",
  "events": [
    {
      "event_id": "event-001",
      "event": "session_start",
      "table_id": 3,
      "timestamp": "2026-10-04T10:05:00+07:00",
      "data": {}
    },
    {
      "event_id": "event-002",
      "event": "game_start",
      "table_id": 3,
      "timestamp": "2026-10-04T10:05:01+07:00",
      "data": {}
    }
  ]
}
```

Response:

```json
{
  "accepted": ["event-001"],
  "duplicates": ["event-002"],
  "rejected": [],
  "conflicts": [],
  "server_state_version": 182
}
```

---

# 23. Synchronization Algorithm

When Wi-Fi reconnects:

```text
OFFLINE
   |
   v
CONNECT
   |
   v
AUTHENTICATE
   |
   v
SEND PENDING EVENTS
   |
   +-- accepted -> mark synced
   |
   +-- duplicate -> mark synced
   |
   +-- rejected -> keep in error queue
   |
   +-- conflict -> reconciliation
   |
   v
GET SERVER STATE
   |
   v
RECONCILE
   |
   v
SYNCED
```

Do not delete failed events automatically.

---

# 24. State Recovery After ESP32 Reboot

Scenario:

```text
Wi-Fi OFF
Table 05 playing
ESP32 power failure
ESP32 restarts
```

The ESP32 must:

1. Load persistent local state
2. Restore Table 05
3. Restore score
4. Restore local session/game IDs
5. Restore timer from timestamps
6. Restore unsent event queue
7. Continue table operation
8. Synchronize when network returns

If Wi-Fi is available after boot:

```text
GET /billiard/controller/state
```

and reconcile with the server.

---

# 25. Time Management

Do not store a decrementing timer in the database.

Store:

```text
started_at
ends_at
```

Example:

```text
started_at = 10:00
ends_at    = 12:00
```

The ESP32 calculates:

```python
remaining = ends_at - current_time
```

The countdown is local.

FastAPI owns official timestamps.

Synchronize the ESP32 clock using NTP when possible.

Use UTC internally.

Display:

```text
Asia/Ho_Chi_Minh
```

for the Vietnamese business UI.

---

# 26. Offline Billing

The ESP32 may display an estimated amount while offline.

Example:

```text
OFFLINE

Playing: 01:35
Estimated: 150,000 VND
```

But FastAPI must calculate the official final amount.

When synchronization happens:

```text
ESP32 events
      |
      v
FastAPI
      |
      v
BillingService
      |
      +-- official duration
      +-- official rate
      +-- table fee
      +-- product fee
      +-- package
      +-- discount
      |
      v
Grand Total
```

Never trust `grand_total` sent by ESP32.

---

# 27. Pricing

Create configurable pricing rules.

Supported types:

```text
per_minute
hourly
block
minimum_hour
```

Example:

```text
Hourly rate = 100,000

60 min  = 100,000
90 min  = 150,000
120 min = 200,000
```

Alternative block pricing:

```text
1-60 min    = 100,000
61-120 min  = 200,000
121-180 min = 300,000
```

Pricing logic belongs in:

```text
billing_service.py
```

Do not put billing calculations inside routes or ESP32 firmware.

---

# 28. Price Snapshot

When a session starts, save:

```text
hourly_rate_snapshot
```

If the price changes later:

```text
September = 100,000/hour
October   = 120,000/hour
```

A September session must continue using:

```text
100,000/hour
```

Do not recalculate historical sessions from the current table price.

---

# 29. Products

Use the existing Product module.

Do not duplicate product management.

Session items:

```text
session_items
----------------
id
session_id
product_id
quantity
unit_price
total_price
```

`unit_price` must be the price snapshot at the time of ordering.

Example:

```text
Coca Cola
Product current price: 18,000

Session ordered at old price:
unit_price = 15,000
```

Historical receipts must remain 15,000.

---

# 30. Packages

Support packages such as:

```text
2 hours
500,000 VND

Includes:
Coca Cola x2
Water x1
```

Models:

```text
billiard_packages
----------------
id
name
duration_minutes
price
is_active

billiard_package_items
----------------
id
package_id
product_id
included_quantity
```

Example:

```text
Package:
2 Hours + Drinks

Price: 500,000

Included:
Coke x2
Water x1
```

If customer consumes:

```text
Coke x3
Water x1
Noodles x2
```

then:

```text
Coke:
2 included
1 charged

Water:
1 included
0 charged

Noodles:
2 charged
```

Record actual quantities for inventory/reporting.

---

# 31. Payment

Use the existing Payment module.

Do not create a second payment implementation inside Billiard.

Billiard should provide:

```text
session_id
table_id
table_fee
product_fee
discount
grand_total
payment_method
```

to the Payment service.

After successful payment:

```text
session = paid/completed
table = available
```

The exact implementation must follow the existing Payment module API.

---

# 32. REST API

Recommended API:

## Tables

```text
GET    /billiard/tables
GET    /billiard/tables/active
GET    /billiard/tables/{table_id}
POST   /billiard/tables/{table_id}/start
POST   /billiard/tables/{table_id}/stop
```

## Sessions

```text
GET    /billiard/sessions/{session_id}
POST   /billiard/sessions/{session_id}/items
POST   /billiard/sessions/{session_id}/stop
POST   /billiard/sessions/{session_id}/pay
```

## Games

```text
GET    /billiard/sessions/{session_id}/games
POST   /billiard/sessions/{session_id}/games
POST   /billiard/games/{game_id}/score
POST   /billiard/games/{game_id}/reset
POST   /billiard/games/{game_id}/new
POST   /billiard/games/{game_id}/finish
```

## Packages

```text
GET    /billiard/packages
POST   /billiard/packages
GET    /billiard/packages/{package_id}
PUT    /billiard/packages/{package_id}
DELETE /billiard/packages/{package_id}
```

## Device

```text
GET    /billiard/controller/state
POST   /billiard/controller/events
POST   /billiard/controller/sync
GET    /billiard/controller/status
```

## Reports

```text
GET /billiard/reports/tables/usage
GET /billiard/reports/sessions
GET /billiard/reports/games
GET /billiard/reports/revenue
```

---

# 33. Example Table Dashboard

React should show all tables:

```text
+---------+------------+----------+---------+----------+
| Table   | Status     | Time     | Score   | Current  |
+---------+------------+----------+---------+----------+
| B01     | PLAYING    | 01:24:35 | 08 : 06 | 210,000 |
| B02     | AVAILABLE  |          |         |         |
| B03     | PLAYING    | 00:42:17 | 05 : 03 | 148,000 |
| B04     | RESERVED   |          |         |         |
| B05     | PLAYING    | 02:05:32 | 12 : 10 | 310,000 |
| ...     |            |          |         |         |
| B10     | AVAILABLE  |          |         |         |
+---------+------------+----------+---------+----------+
```

Use WebSocket for real-time updates.

Do not poll every second from React.

---

# 34. WebSocket

Recommended:

```text
WS /billiard/ws
```

Events sent to React:

```text
table_status_changed
session_started
session_stopped
game_started
score_changed
game_finished
payment_completed
device_online
device_offline
device_syncing
```

Example:

```json
{
  "event": "score_changed",
  "table_id": 4,
  "game_id": 203,
  "score_a": 9,
  "score_b": 6
}
```

---

# 35. Device Authentication

The central ESP32 must have its own device credentials.

Do not use the normal user JWT.

Recommended:

```text
device_id
device_api_key
```

Example:

```text
BILLIARD-CONTROLLER-01
```

Use HTTPS when communication crosses an untrusted network.

Validate every device request.

---

# 36. Device Heartbeat

ESP32 periodically sends:

```json
{
  "event": "heartbeat",
  "device_id": "BILLIARD-CONTROLLER-01",
  "timestamp": "2026-10-04T15:30:00Z",
  "data": {
    "wifi_rssi": -52,
    "uptime": 3821,
    "free_memory": 124000
  }
}
```

FastAPI updates:

```text
last_seen
firmware_version
device status
```

A background job can mark the controller offline after a configurable timeout.

---

# 37. Reports

Table usage report:

```text
Table 01
Sessions: 128
Games: 386
Playing time: 412 hours
Table revenue: 18,500,000
Product revenue: 7,200,000
Total revenue: 25,700,000
```

Support filters:

```text
today
yesterday
this week
this month
custom date range
```

Useful statistics:

- sessions per table
- games per table
- total playing minutes
- average session duration
- average games per session
- table revenue
- product revenue
- package revenue
- total revenue
- most-used tables
- most-ordered products

---

# 38. Concurrency

The backend must prevent:

- Two active sessions on the same table
- Two active games in the same session
- Duplicate score events
- Duplicate session-start events
- Duplicate payment
- Duplicate product order events

Use:

- SQLAlchemy transactions
- Row-level locking where appropriate
- Unique constraints
- Idempotency keys
- Database indexes
- Decimal/Numeric for money

For PostgreSQL, use a partial unique index for active sessions per table.

---

# 39. Security

Validate all:

- table IDs
- session IDs
- game IDs
- product IDs
- quantities
- score deltas
- event IDs
- device IDs
- timestamps
- package IDs

Never trust these values from ESP32:

```text
grand_total
table_fee
product_fee
duration
hourly_rate
payment status
```

FastAPI calculates the official values.

---

# 40. Testing

Create tests for:

```text
test_table_service.py
test_session_service.py
test_game_service.py
test_billing_service.py
test_package_service.py
test_event_service.py
test_device_service.py
test_sync_service.py
```

Minimum test cases:

1. Start available table
2. Reject start on playing table
3. Stop active session
4. Calculate duration
5. Calculate table fee
6. Snapshot hourly rate
7. Create game
8. Add score
9. Prevent negative score
10. Reset score
11. Start new game
12. Multiple games in one session
13. Ten tables operating simultaneously
14. Add product
15. Snapshot product price
16. Package included product
17. Extra product outside package
18. Successful payment
19. Duplicate payment
20. Duplicate ESP32 event
21. Offline event replay
22. Reconnect synchronization
23. ESP32 reboot recovery
24. Conflicting state
25. Device heartbeat
26. Device offline detection
27. RS485 invalid packet
28. RS485 retry
29. Concurrent table start
30. Historical billing after price change

---

# 41. Alembic

Create migrations for:

```text
billiard_tables
table_sessions
session_items
table_games
billiard_pricing_rules
billiard_packages
billiard_package_items
billiard_devices
device_events
```

Ensure:

- Foreign keys
- Indexes
- Unique constraints
- Partial unique index for active sessions
- Proper decimal precision
- Timezone-aware timestamps

---

# 42. Implementation Order

Implement in this order:

## Phase 1 — Database

1. Tables
2. Sessions
3. Session items
4. Games
5. Pricing rules
6. Packages
7. Devices
8. Device events

## Phase 2 — Backend

1. Table service
2. Session service
3. Game service
4. Billing service
5. Package service
6. Device service
7. Event service

## Phase 3 — API

1. Table endpoints
2. Session endpoints
3. Game endpoints
4. Package endpoints
5. Payment integration
6. Device endpoints
7. Sync endpoints
8. Report endpoints

## Phase 4 — ESP32

1. Wi-Fi
2. API client
3. Local state
4. Display abstraction
5. Button input
6. RS485
7. Event queue
8. Persistent storage
9. Sync manager
10. Reboot recovery

## Phase 5 — React

1. Ten-table dashboard
2. Table detail
3. Game scoreboard
4. Product ordering
5. Package selection
6. Billing
7. Payment
8. Reports
9. Device status

## Phase 6 — Testing

Test online, offline, reconnect, reboot, duplicate events, and concurrent table usage.

---

# 43. Critical Business Rules

These rules must remain consistent throughout the codebase.

### Rule 1

One central ESP32 manages all tables.

### Rule 2

A table can have only one active session.

### Rule 3

A session can contain multiple games.

### Rule 4

Starting a new game does not restart billing.

### Rule 5

Score can be changed locally when offline.

### Rule 6

Offline events must survive reboot.

### Rule 7

Offline events must synchronize automatically after reconnect.

### Rule 8

Duplicate events must be idempotent.

### Rule 9

FastAPI owns official billing.

### Rule 10

FastAPI owns official payment state.

### Rule 11

ESP32 never determines the final bill.

### Rule 12

Product prices are snapshotted when ordered.

### Rule 13

Table rates are snapshotted when a session starts.

### Rule 14

Countdown is derived from timestamps, not a database counter.

### Rule 15

`NEW GAME` creates a new game but keeps the same session.

### Rule 16

Payment is handled by the existing Payment module.

### Rule 17

Products are handled by the existing Product module.

### Rule 18

Authentication/authorization is handled by the existing User/Auth module.

---

# 44. Example Complete Flow — Online

```text
Customer arrives
       |
       v
Select Table 01
       |
       v
START
       |
       v
FastAPI creates Session #1001
       |
       v
ESP32 receives session state
       |
       v
Table 01 displays:
2:00:00
Start 09:00
End 11:00
       |
       v
Player scores
       |
       v
ESP32 -> FastAPI
       |
       v
Game score updated
       |
       v
Customer orders drinks
       |
       v
Session items added
       |
       v
NEW GAME
       |
       v
Game 1 completed
Game 2 created
       |
       v
STOP
       |
       v
FastAPI calculates bill
       |
       v
Payment module
       |
       v
Table 01 AVAILABLE
```

---

# 45. Example Complete Flow — Offline

```text
Wi-Fi disconnects
       |
       v
ESP32 enters OFFLINE
       |
       v
Customer uses Table 03
       |
       v
START locally
       |
       v
Game 1 starts
       |
       v
A +1
A +1
B +1
       |
       v
NEW GAME
       |
       v
Game 2 starts
       |
       v
STOP locally
       |
       v
All events stored locally
       |
       v
ESP32 keeps operating
       |
       v
Wi-Fi returns
       |
       v
SYNCING
       |
       v
FastAPI receives events
       |
       v
Idempotency validation
       |
       v
Server records created
       |
       v
Billing calculated
       |
       v
ESP32 receives server state
       |
       v
SYNCED
```

---

# 46. Development Standards

Use:

- Python type hints
- Pydantic v2
- SQLAlchemy 2.x typed mappings
- Async database access where the existing project uses async
- Service layer for business logic
- Controllers for orchestration
- Routes for HTTP concerns
- Dependency injection
- Decimal for money
- UTC timestamps
- Clear domain exceptions
- Structured logging
- Alembic migrations
- Automated tests

Avoid:

- Business logic inside routes
- Business logic inside ESP32 display code
- Floating point money
- Hardcoded table numbers
- Hardcoded product prices
- Hardcoded billing rules
- Duplicate Product logic
- Duplicate Payment logic
- User JWT credentials embedded in firmware
- Per-second database writes
- Deleting unsynchronized events

---

# 47. Definition of Done

The Bida module is complete when:

- [ ] 10 tables can operate independently
- [ ] One central ESP32 controls all 10 tables
- [ ] Each table has its own display/input node
- [ ] RS485 communication works
- [ ] Tables can start/stop sessions
- [ ] Sessions track official start/end times
- [ ] Billing supports configurable pricing
- [ ] Multiple games can exist in one session
- [ ] Scores can be increased/decreased
- [ ] Scores cannot become negative
- [ ] New Game resets the game but not the session
- [ ] Products can be added to sessions
- [ ] Product prices are snapshotted
- [ ] Packages can include products
- [ ] Extra products are charged correctly
- [ ] Payment uses the existing Payment module
- [ ] Table becomes available after successful completion/payment according to configured workflow
- [ ] React dashboard displays all tables
- [ ] WebSocket provides real-time updates
- [ ] ESP32 works without Wi-Fi
- [ ] Offline events are persisted
- [ ] ESP32 survives reboot while offline
- [ ] Reconnect automatically synchronizes events
- [ ] Duplicate events are safely ignored
- [ ] State conflicts are detected
- [ ] FastAPI recalculates official billing
- [ ] Reports show table usage and revenue
- [ ] Automated tests cover online/offline/reconnect scenarios

---

# 48. Final Design Principle

The system should behave as:

```text
              PHYSICAL WORLD
                    |
                    v
             Central ESP32
                    |
             local/offline
                    |
                    v
              FastAPI
                    |
          authoritative state
                    |
        +-----------+-----------+
        |           |           |
      Tables      Product     Payment
        |
      Games
        |
      Billing
```

The central ESP32 must be **offline-capable but not business-authoritative**.

FastAPI must be **business-authoritative but not required for every physical button press**.

This separation allows the billiard hall to continue operating during Wi-Fi/backend outages while preserving reliable billing, score history, product consumption, payment records, and table usage statistics after synchronization.
