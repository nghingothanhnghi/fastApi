#!/usr/bin/env python3
"""
Script to add multiple actuators of the same type to demonstrate multiple actuator functionality
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from app.database import SessionLocal
from app.hydro_system.models.actuator import HydroActuator
from app.hydro_system.schemas.actuator import HydroActuatorCreate
from app.hydro_system.services.actuator_service import hydro_actuator_service
from sqlalchemy import text

def add_multiple_actuators():
    """Add multiple actuators of the same type for testing"""
    db = SessionLocal()
    try:
        print("=== ADDING MULTIPLE ACTUATORS FOR TESTING ===\n")
        
        # Check current device
        device_result = db.execute(text("SELECT id, name FROM devices_hydro LIMIT 1")).fetchone()
        if not device_result:
            print("❌ No device found. Please create a device first.")
            return
        
        device_id = device_result[0]
        device_name = device_result[1]
        print(f"📱 Using Device: ID={device_id}, Name={device_name}")
        
        # Define multiple actuators to add
        new_actuators = [
            # Multiple pumps
            {
                "type": "pump",
                "name": "Pump B - Zone 2",
                "pin": "D6",
                "port": 6,
                "device_id": device_id,
                "is_active": True,
                "default_state": False,
                "sensor_key": "moisture_zone2"
            },
            {
                "type": "pump", 
                "name": "Pump C - Zone 3",
                "pin": "D7",
                "port": 7,
                "device_id": device_id,
                "is_active": True,
                "default_state": False,
                "sensor_key": "moisture_zone3"
            },
            # Multiple lights
            {
                "type": "light",
                "name": "Grow Light B - Seedling Area",
                "pin": "D8",
                "port": 8,
                "device_id": device_id,
                "is_active": True,
                "default_state": False,
                "sensor_key": "light_seedling"
            },
            {
                "type": "light",
                "name": "Grow Light C - Flowering Area", 
                "pin": "D9",
                "port": 9,
                "device_id": device_id,
                "is_active": True,
                "default_state": False,
                "sensor_key": "light_flowering"
            },
            # Multiple fans
            {
                "type": "fan",
                "name": "Intake Fan",
                "pin": "D10",
                "port": 10,
                "device_id": device_id,
                "is_active": True,
                "default_state": False,
                "sensor_key": "temperature"
            },
            {
                "type": "fan",
                "name": "Circulation Fan",
                "pin": "D11", 
                "port": 11,
                "device_id": device_id,
                "is_active": True,
                "default_state": False,
                "sensor_key": "humidity"
            },
            # Multiple valves
            {
                "type": "valve",
                "name": "Nutrient Valve A",
                "pin": "D12",
                "port": 12,
                "device_id": device_id,
                "is_active": True,
                "default_state": False,
                "sensor_key": "ph_level"
            },
            {
                "type": "valve",
                "name": "Nutrient Valve B",
                "pin": "D13",
                "port": 13,
                "device_id": device_id,
                "is_active": True,
                "default_state": False,
                "sensor_key": "ec_level"
            }
        ]
        
        print(f"➕ Adding {len(new_actuators)} new actuators...\n")
        
        added_count = 0
        for actuator_data in new_actuators:
            try:
                # Check if actuator with same port already exists
                existing = db.execute(text(
                    "SELECT id FROM hydro_actuators WHERE device_id = :device_id AND port = :port"
                ), {"device_id": device_id, "port": actuator_data["port"]}).fetchone()
                
                if existing:
                    print(f"⚠️  Skipping {actuator_data['name']} - Port {actuator_data['port']} already in use")
                    continue
                
                # Create actuator
                actuator_create = HydroActuatorCreate(**actuator_data)
                new_actuator = hydro_actuator_service.create_actuator(db, actuator_create)
                
                print(f"✅ Added: {new_actuator.name} (ID: {new_actuator.id}, Type: {new_actuator.type}, Port: {new_actuator.port})")
                added_count += 1
                
            except Exception as e:
                print(f"❌ Failed to add {actuator_data['name']}: {e}")
        
        print(f"\n🎉 Successfully added {added_count} new actuators!")
        
        # Show updated summary
        print(f"\n📊 Updated Actuator Summary:")
        actuator_counts = db.execute(text("""
            SELECT type, COUNT(*) as count 
            FROM hydro_actuators 
            WHERE device_id = :device_id 
            GROUP BY type 
            ORDER BY type
        """), {"device_id": device_id}).fetchall()
        
        for row in actuator_counts:
            actuator_type, count = row
            print(f"  - {actuator_type}: {count} units")
        
    except Exception as e:
        print(f"❌ Error adding actuators: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    add_multiple_actuators()