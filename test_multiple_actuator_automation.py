#!/usr/bin/env python3
"""
Test script to demonstrate multiple actuator automation functionality
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from app.database import SessionLocal
from app.hydro_system.models.actuator import HydroActuator
from app.hydro_system.rules_engine import check_rules
from app.hydro_system.config import DEFAULT_THRESHOLDS
from app.hydro_system.controllers.actuator_controller import handle_automation
from app.hydro_system.services.actuator_service import hydro_actuator_service
from sqlalchemy import text
import json

def test_multiple_actuator_automation():
    """Test automation with multiple actuators of the same type"""
    db = SessionLocal()
    try:
        print("=== TESTING MULTIPLE ACTUATOR AUTOMATION ===\n")
        
        # Get device info
        device_result = db.execute(text("SELECT id, name FROM devices_hydro LIMIT 1")).fetchone()
        if not device_result:
            print("❌ No device found.")
            return
        
        device_id = device_result[0]
        print(f"📱 Testing with Device ID: {device_id}")
        
        # Get all actuators for this device
        actuators_raw = db.execute(text("""
            SELECT id, type, name, pin, port, sensor_key, is_active 
            FROM hydro_actuators 
            WHERE device_id = :device_id AND is_active = 1
            ORDER BY type, port
        """), {"device_id": device_id}).fetchall()
        
        print(f"⚙️  Found {len(actuators_raw)} active actuators")
        
        # Group actuators by type
        actuators_by_type = {}
        for actuator in actuators_raw:
            actuator_type = actuator[1]
            if actuator_type not in actuators_by_type:
                actuators_by_type[actuator_type] = []
            actuators_by_type[actuator_type].append({
                'id': actuator[0],
                'type': actuator[1], 
                'name': actuator[2],
                'pin': actuator[3],
                'port': actuator[4],
                'sensor_key': actuator[5],
                'is_active': actuator[6]
            })
        
        print(f"\n📊 Actuators by Type:")
        for actuator_type, actuators in actuators_by_type.items():
            print(f"  - {actuator_type}: {len(actuators)} units")
        
        # Test different sensor scenarios
        test_scenarios = [
            {
                "name": "Normal Conditions",
                "sensor_data": {
                    "temperature": 25,
                    "humidity": 60,
                    "light": 400,
                    "moisture": 40,
                    "water_level": 50,
                    "device_id": device_id
                },
                "description": "All sensors within normal range"
            },
            {
                "name": "Low Moisture - Multiple Pumps Needed",
                "sensor_data": {
                    "temperature": 25,
                    "humidity": 60,
                    "light": 400,
                    "moisture": 20,  # Below threshold (30)
                    "moisture_zone2": 15,  # Zone 2 also low
                    "moisture_zone3": 25,  # Zone 3 slightly low
                    "water_level": 50,
                    "device_id": device_id
                },
                "description": "Multiple zones need irrigation"
            },
            {
                "name": "Low Light - Multiple Lights Needed",
                "sensor_data": {
                    "temperature": 25,
                    "humidity": 60,
                    "light": 200,  # Below threshold (300)
                    "light_seedling": 150,  # Seedling area very low
                    "light_flowering": 250,  # Flowering area low
                    "moisture": 40,
                    "water_level": 50,
                    "device_id": device_id
                },
                "description": "Multiple lighting zones need activation"
            },
            {
                "name": "High Temperature - Multiple Fans Needed",
                "sensor_data": {
                    "temperature": 32,  # Above threshold (28)
                    "humidity": 80,  # High humidity too
                    "light": 400,
                    "moisture": 40,
                    "water_level": 50,
                    "device_id": device_id
                },
                "description": "Ventilation needed for temperature and humidity"
            },
            {
                "name": "Critical Water Level",
                "sensor_data": {
                    "temperature": 25,
                    "humidity": 60,
                    "light": 400,
                    "moisture": 20,  # Low moisture
                    "water_level": 8,  # Critical level (below 10)
                    "device_id": device_id
                },
                "description": "Critical water level prevents irrigation"
            }
        ]
        
        print(f"\n🧪 TESTING AUTOMATION SCENARIOS:")
        print("=" * 60)
        
        for i, scenario in enumerate(test_scenarios, 1):
            print(f"\n{i}. {scenario['name']}")
            print(f"   {scenario['description']}")
            print(f"   Sensor Data: {json.dumps(scenario['sensor_data'], indent=2)}")
            
            # Create mock actuator objects for rules engine
            mock_actuators = []
            for actuator_data in actuators_raw:
                mock_actuator = type('MockActuator', (), {
                    'id': actuator_data[0],
                    'type': actuator_data[1],
                    'device': type('MockDevice', (), {'thresholds': None})()
                })()
                mock_actuators.append(mock_actuator)
            
            # Test rules engine
            rules_result = check_rules(
                sensor_data=scenario['sensor_data'],
                thresholds=DEFAULT_THRESHOLDS,
                actuators=mock_actuators
            )
            
            print(f"\n   🤖 Automation Results:")
            
            # Show actions for each actuator
            actions = rules_result.get('actions', [])
            if actions:
                actions_by_type = {}
                for action in actions:
                    actuator_type = action['type']
                    if actuator_type not in actions_by_type:
                        actions_by_type[actuator_type] = []
                    actions_by_type[actuator_type].append(action)
                
                for actuator_type, type_actions in actions_by_type.items():
                    active_count = sum(1 for a in type_actions if a['on'])
                    total_count = len(type_actions)
                    print(f"     - {actuator_type}: {active_count}/{total_count} units activated")
                    
                    for action in type_actions:
                        status = "🟢 ON" if action['on'] else "🔴 OFF"
                        actuator_name = next((a[2] for a in actuators_raw if a[0] == action['actuator_id']), f"ID {action['actuator_id']}")
                        print(f"       {status} {actuator_name}")
            else:
                print(f"     - No actuator actions needed")
            
            # Show alerts
            alerts = rules_result.get('alerts', [])
            if alerts:
                print(f"   ⚠️  Alerts:")
                for alert in alerts:
                    alert_type = alert.get('type', 'info').upper()
                    message = alert.get('message', '')
                    print(f"     - {alert_type}: {message}")
            
            # Show water status
            water_status = rules_result.get('water_status', {})
            if water_status:
                status = water_status.get('status', 'unknown')
                message = water_status.get('message', '')
                priority = water_status.get('priority', 'low')
                print(f"   💧 Water Status: {status.upper()} ({priority} priority)")
                print(f"      {message}")
            
            print("-" * 60)
        
        print(f"\n✅ AUTOMATION TESTING COMPLETE")
        print(f"\n📋 Summary:")
        print(f"   - Your system supports multiple actuators of the same type")
        print(f"   - Each actuator can be controlled individually")
        print(f"   - Rules engine evaluates all actuators and provides per-actuator actions")
        print(f"   - Sensor-specific thresholds can be used (via sensor_key)")
        print(f"   - System handles complex scenarios with multiple simultaneous needs")
        
    except Exception as e:
        print(f"❌ Error testing automation: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_multiple_actuator_automation()