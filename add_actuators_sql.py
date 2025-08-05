#!/usr/bin/env python3
"""
Script to add multiple actuators using direct SQL to avoid relationship issues
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from app.database import SessionLocal
from sqlalchemy import text
from datetime import datetime

def add_multiple_actuators_sql():
    """Add multiple actuators using direct SQL"""
    db = SessionLocal()
    try:
        print("=== ADDING MULTIPLE ACTUATORS VIA SQL ===\n")
        
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
            ("pump", "Pump B - Zone 2", "D6", 6, device_id, True, False, "moisture_zone2"),
            ("pump", "Pump C - Zone 3", "D7", 7, device_id, True, False, "moisture_zone3"),
            # Multiple lights
            ("light", "Grow Light B - Seedling Area", "D8", 8, device_id, True, False, "light_seedling"),
            ("light", "Grow Light C - Flowering Area", "D9", 9, device_id, True, False, "light_flowering"),
            # Multiple fans
            ("fan", "Intake Fan", "D10", 10, device_id, True, False, "temperature"),
            ("fan", "Circulation Fan", "D11", 11, device_id, True, False, "humidity"),
            # Multiple valves
            ("valve", "Nutrient Valve A", "D12", 12, device_id, True, False, "ph_level"),
            ("valve", "Nutrient Valve B", "D13", 13, device_id, True, False, "ec_level"),
        ]
        
        print(f"➕ Adding {len(new_actuators)} new actuators...\n")
        
        added_count = 0
        current_time = datetime.now().isoformat()
        
        for actuator_data in new_actuators:
            actuator_type, name, pin, port, device_id, is_active, default_state, sensor_key = actuator_data
            
            try:
                # Check if actuator with same port already exists
                existing = db.execute(text(
                    "SELECT id FROM hydro_actuators WHERE device_id = :device_id AND port = :port"
                ), {"device_id": device_id, "port": port}).fetchone()
                
                if existing:
                    print(f"⚠️  Skipping {name} - Port {port} already in use")
                    continue
                
                # Insert actuator directly
                db.execute(text("""
                    INSERT INTO hydro_actuators 
                    (type, name, pin, port, is_active, default_state, device_id, sensor_key, created_at) 
                    VALUES 
                    (:type, :name, :pin, :port, :is_active, :default_state, :device_id, :sensor_key, :created_at)
                """), {
                    "type": actuator_type,
                    "name": name,
                    "pin": pin,
                    "port": port,
                    "is_active": is_active,
                    "default_state": default_state,
                    "device_id": device_id,
                    "sensor_key": sensor_key,
                    "created_at": current_time
                })
                
                db.commit()
                print(f"✅ Added: {name} (Type: {actuator_type}, Port: {port})")
                added_count += 1
                
            except Exception as e:
                print(f"❌ Failed to add {name}: {e}")
                db.rollback()
        
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
        
        total_actuators = 0
        for row in actuator_counts:
            actuator_type, count = row
            print(f"  - {actuator_type}: {count} units")
            total_actuators += count
        
        print(f"\n📈 Total Actuators: {total_actuators}")
        
        # Show multiple actuator types
        multiple_types = [row for row in actuator_counts if row[1] > 1]
        if multiple_types:
            print(f"\n🔥 Multiple Actuator Types Found:")
            for actuator_type, count in multiple_types:
                print(f"  ✅ {actuator_type}: {count} units")
                
                # Show individual actuators of this type
                actuators = db.execute(text("""
                    SELECT id, name, pin, port, sensor_key 
                    FROM hydro_actuators 
                    WHERE device_id = :device_id AND type = :type 
                    ORDER BY port
                """), {"device_id": device_id, "type": actuator_type}).fetchall()
                
                for actuator in actuators:
                    print(f"    - ID: {actuator[0]}, Name: {actuator[1]}, Pin: {actuator[2]}, Port: {actuator[3]}, Sensor: {actuator[4] or 'N/A'}")
        
    except Exception as e:
        print(f"❌ Error adding actuators: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    add_multiple_actuators_sql()