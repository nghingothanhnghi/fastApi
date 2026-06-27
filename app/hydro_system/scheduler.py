# app/hydro_system/scheduler.py
# Description: This module handles scheduling tasks for collecting and processing sensor data.
# from app.hydro_system.models.device import HydroDevice
# from app.hydro_system.models.sensor_data import SensorData
# from app.hydro_system.sensors import read_sensors
# from app.hydro_system.services.automation_service import automation_service
# from app.database import SessionLocal
from app.hydro_system.jobs.sensor_job import (
    collect_and_process
)

from app.hydro_system.jobs.batch_job import (
    update_batch_stages
)
from app.utils.scheduler import add_job, remove_job
from app.core.logging_config import get_logger

logger = get_logger(__name__)

SENSOR_JOB_ID = "sensor_collect_job"
BATCH_STAGE_JOB_ID = "batch_stage_update_job"

# def collect_and_process():
#     session = SessionLocal()
#     try:
#         devices = session.query(HydroDevice).filter(HydroDevice.is_active == True).all()

#         if not devices:
#             logger.warning("No active devices found. Skipping sensor collection.")
#             return

#         for device in devices:
#             device_id = device.id
#             logger.info(f"🔄 Collecting data for device: {device_id}")

#             try:
#                 sensor_data = {}
#                 try:
#                     sensor_data = read_sensors(device_id=device_id)
#                     logger.info(f"Device {device_id} sensor data: {sensor_data}")

#                     # Only keep fields that exist in SensorData model
#                     allowed_keys = {"temperature", "humidity", "light", "moisture", "water_level", "ec", "ppm", "device_id"}
#                     clean_data = {k: v for k, v in sensor_data.items() if k in allowed_keys}

#                     entry = SensorData(**clean_data)
#                     session.add(entry)
#                     session.commit()
#                 except Exception as sensor_error:
#                     logger.error(f"⚠️ Failed reading sensors for device {device_id}: {sensor_error}")
#                     # Still proceed to handle_automation for schedules

#                 # ⚡ Run control loop
#                 automation_service.run_control_loop(
#                     db=session,
#                     sensor_data=sensor_data,
#                     device_id=device_id
#                 )

#             except Exception as e:
#                 logger.error(f"❌ Failed processing device {device_id}: {e}")

#     except Exception as e:
#         logger.error(f"Sensor collection failed: {e}")
#     finally:
#         session.close()


# def update_batch_stages():
#     """
#     Background job to automatically update plant batch stages based on days_growing.
#     """
#     session = SessionLocal()
#     try:
#         automation_service.run_growth_cycle(session)
#         logger.info("✅ Batch stages updated via AutomationService")
#     except Exception as e:
#         logger.error(f"Failed to update batch stages: {e}")
#         session.rollback()
#     finally:
#         session.close()


# def start_sensor_job():
#     # ✅ Use global scheduler to add job
#     add_job(collect_and_process, job_id=SENSOR_JOB_ID, job_name="Sensor Collect Job", seconds=60)
#     # Also ensure batch stage job is running
#     start_batch_stage_job()
#     logger.info("Sensor and Batch jobs scheduled.")

# def start_batch_stage_job():
#     """Start the background job for updating batch stages (runs once a day)"""
#     # Run once every 6 hours or once a day. Let's start with every 12 hours.
#     add_job(update_batch_stages, job_id=BATCH_STAGE_JOB_ID, job_name="Batch Stage Update Job", hours=12)
#     logger.info("Batch stage update job scheduled.")

# def stop_sensor_job():
#     remove_job(SENSOR_JOB_ID)  # Use the remove_job function from utils.scheduler 
#     stop_batch_stage_job()
#     logger.warning("Hydro system jobs stopped (Sensor + Batch)")

# def stop_batch_stage_job():
#     remove_job(BATCH_STAGE_JOB_ID)
#     logger.info("Batch stage update job stopped.")

# def restart_sensor_job():
#     stop_sensor_job()  # Stop both jobs
#     start_sensor_job()  # Start both jobs
#     logger.info("Hydro scheduler restarted.") 



# ==========================================================
# START
# ==========================================================

def start_sensor_job():
    """
    Start sensor collection + automation loop.
    Runs every minute.
    """
    add_job(
        collect_and_process,
        job_id=SENSOR_JOB_ID,
        job_name="Sensor Collect Job",
        seconds=60,
    )

    start_batch_stage_job()

    logger.info("✅ Sensor and Batch jobs scheduled")


def start_batch_stage_job():
    """
    Update plant batch stages automatically.
    """
    add_job(
        update_batch_stages,
        job_id=BATCH_STAGE_JOB_ID,
        job_name="Batch Stage Update Job",
        hours=12,
    )

    logger.info("✅ Batch stage update job scheduled")


# ==========================================================
# STOP
# ==========================================================

def stop_sensor_job():
    """
    Stop all hydro jobs.
    """
    remove_job(SENSOR_JOB_ID)

    stop_batch_stage_job()

    logger.warning("🛑 Hydro system jobs stopped")


def stop_batch_stage_job():
    """
    Stop batch stage updater.
    """
    remove_job(BATCH_STAGE_JOB_ID)

    logger.info("🛑 Batch stage update job stopped")


# ==========================================================
# RESTART
# ==========================================================

def restart_sensor_job():
    """
    Restart all hydro jobs.
    """
    stop_sensor_job()
    start_sensor_job()

    logger.info("🔄 Hydro scheduler restarted")
