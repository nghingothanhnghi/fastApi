# app/hydro_system/state_manager.py
# This file is used to manage the state of devices in the hydroponic system.
_state = {
    "pump": False,
    "light": False,
    "scheduler": False
}

def get_state(device):
    return _state.get(device, None)

def set_state(device, value):
    _state[device] = value
