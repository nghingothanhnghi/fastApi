from app.hydro_system import sensors, device_controller as controller, state_manager
from app.hydro_system.scheduler import start_sensor_job, stop_sensor_job, restart_sensor_job

def get_system_status():
    return {
        "temperature": sensors.read_temperature(),
        "humidity": sensors.read_humidity(),
        "pump_state": state_manager.get_state("pump"),
        "light_state": state_manager.get_state("light"),
        "scheduler_state": state_manager.get_state("scheduler")
    }

def control_pump(on: bool):
    if on:
        controller.turn_pump_on()
    else:
        controller.turn_pump_off()
    state_manager.set_state("pump", on)

def control_light(on: bool):
    if on:
        controller.turn_light_on()
    else:
        controller.turn_light_off()
    state_manager.set_state("light", on)

def scheduler_control(action: str):
    if action == "start":
        start_sensor_job()
    elif action == "stop":
        stop_sensor_job()
    elif action == "restart":
        restart_sensor_job()
