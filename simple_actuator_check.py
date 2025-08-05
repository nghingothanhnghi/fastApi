#!/usr/bin/env python3
"""
Simple script to check actuators using raw SQL
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from app.database import SessionLocal
from sqlalchemy import text

def check_actuators_simple():
    """Check actuators using raw SQL queries"""
    db = SessionLocal()
    try:
        print("=== HYDRO SYSTEM ACTUATOR ANALYSIS ===\n")
        
        # Check if tables exist
        tables_result = db.execute(text("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name IN ('devices_hydro', 'hydro_actuators')
        """)).fetchall()
        
        existing_tables = [row[0] for row in tables_result]
        print(f"📋 Existing tables: {existing_tables}")
        
        if 'devices_hydro' in existing_tables:
            # Check devices
            device_count = db.execute(text("SELECT COUNT(*) FROM devices_hydro")).scalar()
            print(f"📱 Total Devices: {device_count}")
            
            if device_count > 0:
                devices = db.execute(text("SELECT id, name, device_id, is_active FROM devices_hydro")).fetchall()
                for device in devices:
                    print(f"  - ID: {device[0]}, Name: {device[1]}, Device ID: {device[2]}, Active: {device[3]}")
        else:
            print("❌ devices_hydro table not found")
        
        print()
        
        if 'hydro_actuators' in existing_tables:
            # Check actuators
            actuator_count = db.execute(text("SELECT COUNT(*) FROM hydro_actuators")).scalar()
            print(f"⚙️  Total Actuators: {actuator_count}")
            
            if actuator_count == 0:
                print("❌ No actuators found in database!")
                print("\n💡 This means your system has no physical actuators configured.")
                print("   The rules engine will work with DEFAULT_ACTUATORS fallback logic.")
                return
            
            # Get all actuators
            actuators = db.execute(text("""
                SELECT id, type, name, pin, port, device_id, is_active, default_state, sensor_key 
                FROM hydro_actuators 
                ORDER BY type, device_id, port
            """)).fetchall()
            
            # Group by type
            actuator_types = {}
            for actuator in actuators:
                actuator_type = actuator[1]  # type column
                if actuator_type not in actuator_types:
                    actuator_types[actuator_type] = []
                actuator_types[actuator_type].append(actuator)
            
            print(f"\n📊 Actuators by Type:")
            for actuator_type, type_actuators in actuator_types.items():
                print(f"\n🔧 {actuator_type.upper()} ({len(type_actuators)} units):")
                for actuator in type_actuators:
                    print(f"  - ID: {actuator[0]}")
                    print(f"    Name: {actuator[2] or 'Unnamed'}")
                    print(f"    Pin: {actuator[3] or 'N/A'}")
                    print(f"    Port: {actuator[4]}")
                    print(f"    Device ID: {actuator[5]}")
                    print(f"    Active: {actuator[6]}")
                    print(f"    Default State: {actuator[7]}")
                    print(f"    Sensor Key: {actuator[8] or 'N/A'}")
                    print()
            
            # Check for multiple actuators of same type
            print("🔍 Multiple Actuator Analysis:")
            multiple_types = {k: v for k, v in actuator_types.items() if len(v) > 1}
            
            if multiple_types:
                print("✅ Found multiple actuators of same type:")
                for actuator_type, type_actuators in multiple_types.items():
                    print(f"  - {actuator_type}: {len(type_actuators)} units")
                    device_distribution = {}
                    for actuator in type_actuators:
                        device_id = actuator[5]  # device_id column
                        if device_id not in device_distribution:
                            device_distribution[device_id] = 0
                        device_distribution[device_id] += 1
                    
                    print(f"    Distribution across devices: {device_distribution}")
            else:
                print("⚠️  No multiple actuators of same type found.")
                print("   Each actuator type has only 1 unit.")
            
            # Check automation compatibility
            print(f"\n🤖 Automation Compatibility:")
            supported_types = ["pump", "light", "fan", "water_pump", "valve"]
            found_types = set(actuator_types.keys())
            
            print(f"  Supported by rules engine: {supported_types}")
            print(f"  Found in database: {list(found_types)}")
            print(f"  ✅ Supported & Present: {list(found_types.intersection(supported_types))}")
            print(f"  ⚠️  Unsupported types: {list(found_types - set(supported_types))}")
            print(f"  ❌ Missing types: {list(set(supported_types) - found_types)}")
            
        else:
            print("❌ hydro_actuators table not found")
        
    except Exception as e:
        print(f"❌ Error checking actuators: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_actuators_simple()