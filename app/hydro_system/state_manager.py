# app/hydro_system/state_manager.py
# This file is used to manage the state of devices in the hydroponic system.

import logging

logger = logging.getLogger(__name__)

_state = {
    "pump": False,
    "light": False,
    "scheduler": False,
    "fan": False,               # ✅ add this
    "water_pump": False,        # ✅ add this
    "water_refill": False,
    "valve": False,
}

def get_state(device):
    return _state.get(device, False)

def set_state(device, value):
    _state[device] = value
    logger.info(f"[STATE_MANAGER] {device} set to {value}")
