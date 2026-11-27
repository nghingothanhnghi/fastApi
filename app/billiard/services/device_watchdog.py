# app/billiard/services/device_watchdog.py
# The ONLY writer of a controller's online/offline status and of billiard_device_status_log.
#  - mark_online:   any authenticated contact from the device (heartbeat, sync, state ...).
#  - sweep_offline: the periodic job; marks silent controllers offline.
# Both use a conditional UPDATE and write the log row only when they won the change, so a
# transition is logged exactly once even with several workers or overlapping runs, and a late
# sweep can never overwrite a heartbeat that arrived meanwhile.
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from app.billiard.models import BilliardDevice, DeviceStatus, DeviceStatusLog
from app.billiard.services import realtime
from app.billiard.utils.billing import as_utc
from app.billiard import config


def offline_after() -> timedelta:
    """Silence longer than this means offline. Read on every call so it can be configured."""
    return timedelta(seconds=config.OFFLINE_AFTER_SECONDS)


def _log(db: Session, device_pk: int, old: DeviceStatus, new: DeviceStatus, at: datetime, reason: str) -> None:
    db.add(DeviceStatusLog(device_id=device_pk, from_status=old.value, to_status=new.value, at=at, reason=reason))


def mark_online(db: Session, device: BilliardDevice, now: Optional[datetime] = None) -> bool:
    """Record contact from the device. Returns True when this call turned it online (one log row)."""
    now = as_utc(now or datetime.now(timezone.utc))
    device.last_seen = now
    previous = device.status
    if previous == DeviceStatus.ONLINE:
        db.flush()
        return False
    won = db.execute(
        update(BilliardDevice)
        .where(BilliardDevice.id == device.id, BilliardDevice.status != DeviceStatus.ONLINE)
        .values(status=DeviceStatus.ONLINE, status_changed_at=now, last_seen=now)
        .execution_options(synchronize_session=False)       # attributes are synced by hand below
    ).rowcount == 1
    set_committed_value(device, "status", DeviceStatus.ONLINE)
    if won:
        set_committed_value(device, "status_changed_at", now)
        _log(db, device.id, previous, DeviceStatus.ONLINE, now, "device contact")
        realtime.publish_after_commit(db, device.client_id, realtime.device_status(device.device_id, "online"))
    db.flush()
    return won


def sweep_offline(db: Session, now: Optional[datetime] = None, after: Optional[timedelta] = None) -> list[BilliardDevice]:
    """Mark stored-online controllers silent for MORE than `after` as offline.

    Returns the devices this call switched (the caller commits, then alerts). A device exactly at
    the threshold is still online, the same rule as DeviceService.effective_status.
    """
    now = as_utc(now or datetime.now(timezone.utc))
    cutoff = now - (after if after is not None else offline_after())
    candidates = db.execute(
        select(BilliardDevice).where(
            BilliardDevice.status == DeviceStatus.ONLINE,
            or_(BilliardDevice.last_seen.is_(None), BilliardDevice.last_seen < cutoff),
        )
    ).scalars().all()

    switched = []
    for device in candidates:
        silent = "never seen" if device.last_seen is None else f"silent for {int((now - as_utc(device.last_seen)).total_seconds())}s"
        won = db.execute(
            update(BilliardDevice)
            .where(
                BilliardDevice.id == device.id,
                BilliardDevice.status == DeviceStatus.ONLINE,
                or_(BilliardDevice.last_seen.is_(None), BilliardDevice.last_seen < cutoff),   # a fresh heartbeat wins
            )
            .values(status=DeviceStatus.OFFLINE, status_changed_at=now)
            .execution_options(synchronize_session=False)
        ).rowcount == 1
        if won:
            _log(db, device.id, DeviceStatus.ONLINE, DeviceStatus.OFFLINE, now, silent)
            set_committed_value(device, "status", DeviceStatus.OFFLINE)
            set_committed_value(device, "status_changed_at", now)
            realtime.publish_after_commit(db, device.client_id, realtime.device_status(device.device_id, "offline"))
            switched.append(device)
    db.flush()
    return switched
