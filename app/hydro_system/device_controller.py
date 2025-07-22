# File: backend/app/hydro_system/device_controller.py
# Description: Hardware control logic

from app.hydro_system.rules_engine import check_rules
from app.hydro_system.state_manager import set_state
import logging

logger = logging.getLogger(__name__)


def turn_pump_on():
    print("Pump turned on")

def turn_pump_off():
    print("Pump turned off")

def turn_light_on():
    print("Light turned on")

def turn_light_off():
    print("Light turned off")

def handle_automation(sensor_data):
    actions = check_rules(sensor_data)

    for device, action in actions.items():
        set_state(device, action)
        logger.info(f"[Automation] Set {device} to {action}")
