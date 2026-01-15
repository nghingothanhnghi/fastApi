+-------------------+        +------------------------+
|  Sensors (ESP32)  |        |   Actuators (Relays)   |
| - Temperature     |        | - Pump, Fan, Light     |
| - Humidity        |        | - Water Pump           |
| - Light           |        +------------------------+
| - Moisture        |                 ^
| - Water Level     |                 |
| - PPM             |                 |
| - EC              |                 |
+--------+----------+                 |
         | Sends sensor data          | GPIO HIGH/LOW
         v                            |
+-------------------+        +------------------------+
|       ESP32       |        |  relay.py update_relays |
| - Reads sensors   |        |  Maps ACTUATOR_STATES   |
| - Calls backend   | ------> updates physical relays
|   /sensor/data    |        +------------------------+
| - Calls backend   |
|   /hydro/status   |
+--------+----------+
         ^
         | Receives actuator states
         | (current_state) from backend
         |
+-------------------+
|     Backend       |
| (FastAPI Server)  |
|                   |
| - Scheduler job   |
|   runs every X s  |
| - Reads last      |
|   sensor data     |
| - Runs automation |
|   rules (check_rules)|
| - Sets actuator   |
|   states in state_manager |
| - Updates current_state |
+-------------------+
         ^
         |
+-------------------+
|   Frontend / API  |
| - Manual override |
|   POST /actuator/{id}/on  |
|   POST /actuator/{id}/off |
| - Updates backend |
|   actuator states in state_manager |
+-------------------+

