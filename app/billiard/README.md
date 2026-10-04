content = r'''# Bida (Billiard) Management Module

Production-oriented specification for a billiard table management system integrated with an existing FastAPI backend, Product module, Payment module, User/Auth module, React POS, and one central ESP32 controller managing up to 10 billiard tables.

---

# 1. Overview

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

Only one central ESP32 is required. There must NOT be one ESP32 per table.

--
# 3. Main Responsibilities

--
***FastAPI owns
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

***Central ESP32 owns
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

***ESP32 must NOT be authoritative for
- Final billing
- Payment status
- Product price
- Grand total
- Official historical revenue
- User permissions

# 4. Recommended Backend Structure

app/
└── modules/
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

Follow the existing project's architecture rather than duplicating infrastructure.

# 5. Database Model

billiard_tables



The code must not hardcode exactly 10 tables, n+table dynamic. The database should support any number of tables.

6. Table Sessions

A TableSession represents one customer/table billing period.

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


Statuses:

active
completed
cancelled

Example:

Table 01

Session #1001
09:00 -> 11:15
Duration: 135 minutes
Rate: 100,000/hour
Table fee: 225,000
Products: 85,000
Grand total: 310,000


# 7. Session vs Game
A session and a game are NOT the same thing. A customer may play multiple games during one paid table session.

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


Starting a new game does NOT stop billing.

8. table_games

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

/////////
Statuses:

active
completed
cancelled

When NEW GAME is pressed:

1. Complete current game
2. Create next game
3. Set both scores to zero
4. Continue the existing table session
5. Do not restart the billing timer

# 9. Score Management

Each table supports:

Player A +
Player A -

Player B +
Player B -

Reset Score
New Game


Rules:

Score cannot become negative.
Every score modification should create an auditable event.
ESP32 can update the physical display immediately.
FastAPI must eventually receive and persist the event.
Duplicate events must not increment the score twice.

Example event:

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



# 10. Electronic Scoreboard

Each physical table has an electronic display and buttons.

Example active display:

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

Idle:

+----------------------+
|      TABLE 01        |
|                      |
|      AVAILABLE       |
|                      |
+----------------------+

Offline:

+----------------------+
|      TABLE 01        |
|                      |
|       08 : 06        |
|       A     B        |
|                      |
|       01:24:35       |
|                      |
|       OFFLINE        |
+----------------------+

The display implementation must be abstracted so the business logic does not depend on a particular display library.

# 11. Central ESP32

Use exactly one central ESP32.

It manages N+ tables:

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
+-- Table N+ state