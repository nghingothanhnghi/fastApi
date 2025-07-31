# app/hydro_system/scheduler.py
# Description: This module handles scheduling tasks for collecting and processing sensor data.
from app.hydro_system.models.device import HydroDevice
from app.hydro_system.models.sensor_data import SensorData
from app.hydro_system.sensors import read_sensors
from app.hydro_system.controllers.actuator_controller import handle_automation
from app.database import SessionLocal
from app.hydro_system.models.sensor_data import SensorData
from app.hydro_system import state_manager
from app.utils.scheduler import add_job, remove_job
import logging

logger = logging.getLogger(__name__)

JOB_ID = "sensor_collect_job"

def collect_and_process():
    session = SessionLocal()
    try:
        devices = session.query(HydroDevice).filter(HydroDevice.is_active == True).all()

        if not devices:
            logger.warning("No active devices found. Skipping sensor collection.")
            return

        for device in devices:
            device_id = device.id
            logger.info(f"🔄 Collecting data for device: {device_id}")

            try:
                sensor_data = read_sensors(device_id=device_id)
                logger.info(f"Device {device_id} sensor data: {sensor_data}")

                entry = SensorData(**sensor_data, device_id=device_id)
                session.add(entry)
                session.commit()

                handle_automation(session, sensor_data, device_id=device_id)

            except Exception as e:
                logger.error(f"❌ Failed processing device {device_id}: {e}")

    except Exception as e:
        logger.error(f"Sensor collection failed: {e}")
    finally:
        session.close()


def start_sensor_job():
    # ✅ Use global scheduler to add job
    add_job(collect_and_process, seconds=60, job_id=JOB_ID, job_name="Sensor Collect Job")
    state_manager.set_state("scheduler", True)
    logger.info("Sensor job scheduled.")

def stop_sensor_job():
    remove_job(JOB_ID)  # Use the remove_job function from utils.scheduler 
    state_manager.set_state("scheduler", False)
    logger.warning("Stop job manually in global scheduler (not yet implemented)")

def restart_sensor_job():
    stop_sensor_job()  # Stop the existing job
    start_sensor_job()  # Start a new job
    logger.info("Scheduler restarted.") 
