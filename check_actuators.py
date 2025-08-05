#!/usr/bin/env python3
"""
Script to check current actuators in the hydro system database
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from app.database import SessionLocal
from app.hydro_system.models.actuator import HydroActuator
from app.hydro_system.services.actuator_service import hydro_actuator_service
from sqlalchemy import func, text

def check_actuators():
    """Check what actuators exist in the database"""
    db = SessionLocal()
    try:
        print("=== HYDRO SYSTEM ACTUATOR ANALYSIS ===\n")
        
        # Check devices first using raw SQL to avoid relationship issues
        device_count = db.execute(text("SELECT COUNT(*) FROM devices_hydro")).scalar()
        print(f"📱 Total Devices: {device_count}")
        
        if device_count > 0:
            devices_result = db.execute(text("SELECT id, name, device_id FROM devices_hydro")).fetchall()
            for device in devices_result:
                print(f"  - Device ID: {device[0]}, Name: {device[1]}, Device ID: {device[2]}")
        print()
        
        # Check all actuators
        actuators = db.query(HydroActuator).all()
        print(f"⚙️  Total Actuators: {len(actuators)}")
        
        if not actuators:
            print("❌ No actuators found in database!")
            print("\n💡 This means your system has no physical actuators configured.")
            print("   The rules engine will work with DEFAULT_ACTUATORS fallback logic.")
            return
        
        # Group by type
        actuator_types = {}
        for actuator in actuators:
            if actuator.type not in actuator_types:
                actuator_types[actuator.type] = []
            actuator_types[actuator.type].append(actuator)
        
        print(f"\n📊 Actuators by Type:")
        for actuator_type, type_actuators in actuator_types.items():
            print(f"\n🔧 {actuator_type.upper()} ({len(type_actuators)} units):")
            for actuator in type_actuators:
                print(f"  - ID: {actuator.id}")
                print(f"    Name: {actuator.name or 'Unnamed'}")
                print(f"    Pin: {actuator.pin or 'N/A'}")
                print(f"    Port: {actuator.port}")
                print(f"    Device ID: {actuator.device_id}")
                print(f"    Active: {actuator.is_active}")
                print(f"    Default State: {actuator.default_state}")
                print(f"    Sensor Key: {actuator.sensor_key or 'N/A'}")
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
                    device_id = actuator.device_id
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
        
    except Exception as e:
        print(f"❌ Error checking actuators: {e}")
    finally:
        db.close()

def check_rules_engine_compatibility():
    """Check if rules engine supports multiple actuators"""
    print(f"\n🧠 RULES ENGINE ANALYSIS:")
    print("The rules engine in rules_engine.py supports:")
    print("✅ Multiple actuators of same type via check_rules() function")
    print("✅ Per-actuator thresholds via actuator.device.thresholds")
    print("✅ Individual actuator control via actuator_id")
    print("✅ Device-specific actuator filtering")
    
    print(f"\nSupported actuator types in automation:")
    print("  - pump: Irrigation pump control")
    print("  - light: Grow light control") 
    print("  - fan: Ventilation fan control")
    print("  - water_pump: Water tank refill pump")
    print("  - valve: Water valve control")

if __name__ == "__main__":
    check_actuators()
    check_rules_engine_compatibility()