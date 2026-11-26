# app/billiard/services/device_alerts.py
# Alert hook for controller status changes. Today it only logs; realtime push (roadmap item I)
# will be added here so the watchdog does not change.
import logging

from app.billiard.models import BilliardDevice

logger = logging.getLogger(__name__)


def notify_device_offline(device: BilliardDevice) -> None:
    """Called once per online -> offline transition, after the change is committed."""
    logger.warning(
        "[Billiard] Controller %s (club %s) is offline. Last seen: %s",
        device.device_id, device.client_id, device.last_seen,
    )
