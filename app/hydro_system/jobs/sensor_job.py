# app/hydro_system/jobs/sensor_job.py

from app.hydro_system.models.device import HydroDevice
from app.hydro_system.models.sensor_data import SensorData
from app.hydro_system.sensors import read_sensors
from app.hydro_system.services.automation_service import automation_service

from app.hydro_system.jobs.base_job import resilient_job
from app.core.logging_config import get_logger

logger = get_logger(__name__)

@resilient_job("sensor_collect")
def collect_and_process(*, db):
    devices = (
        db.query(HydroDevice)
        .filter(HydroDevice.is_active == True)
        .all()
    )

    if not devices:
        logger.warning("No active devices found.")
        return

    for device in devices:
        try:
            sensor_data = read_sensors(
                device_id=device.id
            )

            allowed_keys = {
                "temperature",
                "humidity",
                "light",
                "moisture",
                "water_level",
                "ec",
                "ppm",
                "device_id",
            }

            clean_data = {
                k: v
                for k, v in sensor_data.items()
                if k in allowed_keys
            }

            db.add(SensorData(**clean_data))
            db.commit()

            automation_service.run_control_loop(
                db=db,
                sensor_data=sensor_data,
                device_id=device.id,
            )

        except Exception as e:
            logger.error(
                f"Device {device.id} failed: {e}",
                exc_info=True,
            )

            db.rollback()