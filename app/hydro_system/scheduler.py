# app/hydro_system/scheduler.py
# Description: This module handles scheduling tasks for collecting and processing sensor data.
from app.hydro_system.models.device import HydroDevice
from app.hydro_system.models.sensor_data import SensorData
from app.hydro_system.models.plant_batch import PlantBatch
from app.hydro_system.models.growth_stage import GrowthStage
from app.hydro_system.sensors import read_sensors
from app.hydro_system.controllers.actuator_controller import handle_automation
from app.hydro_system.controllers.recipe_engine_controller import recipe_engine_controller
from app.database import SessionLocal
from app.hydro_system import state_manager
from app.utils.scheduler import add_job, remove_job
from app.core.logging_config import get_logger
from sqlalchemy.orm import joinedload
from datetime import date

logger = get_logger(__name__)

SENSOR_JOB_ID = "sensor_collect_job"
BATCH_STAGE_JOB_ID = "batch_stage_update_job"

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
                sensor_data = {}
                try:
                    sensor_data = read_sensors(device_id=device_id)
                    logger.info(f"Device {device_id} sensor data: {sensor_data}")

                    # Only keep fields that exist in SensorData model
                    allowed_keys = {"temperature", "humidity", "light", "moisture", "water_level", "ec", "ppm", "device_id"}
                    clean_data = {k: v for k, v in sensor_data.items() if k in allowed_keys}

                    entry = SensorData(**clean_data)
                    session.add(entry)
                    session.commit()
                except Exception as sensor_error:
                    logger.error(f"⚠️ Failed reading sensors for device {device_id}: {sensor_error}")
                    # Still proceed to handle_automation for schedules

                handle_automation(session, sensor_data, device_id=device_id)

            except Exception as e:
                logger.error(f"❌ Failed processing device {device_id}: {e}")

    except Exception as e:
        logger.error(f"Sensor collection failed: {e}")
    finally:
        session.close()


def update_batch_stages():
    """
    Background job to automatically update plant batch stages based on days_growing.
    """
    session = SessionLocal()
    try:
        # 1️⃣ Fetch all growing batches
        batches = session.query(PlantBatch).options(
            joinedload(PlantBatch.current_stage)
        ).filter(PlantBatch.status == "growing").all()

        today = date.today()

        for batch in batches:
            # 2️⃣ Calculate days_growing
            days_growing = (today - batch.start_date).days
            logger.debug(f"Checking Batch {batch.id} (Plant: {batch.plant_id}) - Days growing: {days_growing}")

            # 3️⃣ Find the appropriate stage for this plant and day
            new_stage = session.query(GrowthStage).filter(
                GrowthStage.plant_id == batch.plant_id,
                GrowthStage.day_start <= days_growing,
                GrowthStage.day_end >= days_growing
            ).first()

            if new_stage and (not batch.current_stage or batch.current_stage_id != new_stage.id):
                logger.info(f"🚀 Batch {batch.id} stage transition: {batch.current_stage.name if batch.current_stage else 'None'} -> {new_stage.name}")
                
                # 4️⃣ Update batch current stage
                batch.current_stage_id = new_stage.id
                session.add(batch)
                
                # 5️⃣ Apply recipes for the new stage
                # We need to reload the stage with recipes
                full_stage = session.query(GrowthStage).options(
                    joinedload(GrowthStage.recipes)
                ).filter(GrowthStage.id == new_stage.id).first()
                
                if full_stage:
                    recipe_engine_controller.apply_stage_recipes(session, batch, full_stage.recipes)
                
                session.commit()
                logger.info(f"✅ Batch {batch.id} updated to stage {new_stage.name}")

    except Exception as e:
        logger.error(f"Failed to update batch stages: {e}")
        session.rollback()
    finally:
        session.close()


def start_sensor_job():
    # ✅ Use global scheduler to add job
    add_job(collect_and_process, seconds=60, job_id=SENSOR_JOB_ID, job_name="Sensor Collect Job")
    state_manager.set_state("scheduler", True)
    logger.info("Sensor job scheduled.")

def start_batch_stage_job():
    """Start the background job for updating batch stages (runs once a day)"""
    # Run once every 6 hours or once a day. Let's start with every 12 hours.
    add_job(update_batch_stages, hours=12, job_id=BATCH_STAGE_JOB_ID, job_name="Batch Stage Update Job")
    logger.info("Batch stage update job scheduled.")

def stop_sensor_job():
    remove_job(SENSOR_JOB_ID)  # Use the remove_job function from utils.scheduler 
    state_manager.set_state("scheduler", False)
    logger.warning("Stop job manually in global scheduler (not yet implemented)")

def stop_batch_stage_job():
    remove_job(BATCH_STAGE_JOB_ID)
    logger.info("Batch stage update job stopped.")

def restart_sensor_job():
    stop_sensor_job()  # Stop the existing job
    start_sensor_job()  # Start a new job
    logger.info("Scheduler restarted.") 
