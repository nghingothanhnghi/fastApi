# app/billiard/jobs/device_watchdog_job.py
# Periodic check for silent controllers. Registered in main.py
# (see config.BILLIARD_WATCHDOG_INTERVAL_SECONDS and BILLIARD_OFFLINE_AFTER_SECONDS).
import logging

from app.billiard.services import device_alerts, device_watchdog
from app.database import SessionLocal

logger = logging.getLogger(__name__)


def device_watchdog_job() -> None:
    db = SessionLocal()
    try:
        switched = device_watchdog.sweep_offline(db)
        db.commit()                                   # alert only for changes that are saved
        for device in switched:
            try:
                device_alerts.notify_device_offline(device)
            except Exception:                         # an alert problem must not undo or repeat the change
                logger.exception("[Billiard] Offline alert failed for %s", device.device_id)
    except Exception as e:
        logger.error("[Billiard] Device watchdog failed: %s", e, exc_info=True)
        db.rollback()
    finally:
        db.close()
