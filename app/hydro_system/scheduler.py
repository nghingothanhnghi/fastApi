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
