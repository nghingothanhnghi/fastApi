from sqlalchemy.orm import Session, selectinload
from app.hydro_system.models.device import HydroDevice
from app.hydro_system.models.actuator import HydroActuator
from app.hydro_system.services.threshold_service import threshold_service


def _hhmm(t):
    return t.strftime("%H:%M") if t else None


class DeviceConfigService:
    def get_compact_config(self, db: Session, device_id: str):
        device = (
            db.query(HydroDevice)
            .options(
                selectinload(HydroDevice.actuators)
                .selectinload(HydroActuator.schedules)
            )
            .filter(HydroDevice.device_id == device_id)
            .first()
        )
        if not device:
            return None

        t = threshold_service.get_for_device(device)
        thresholds = {k: v for k, v in t.items() if not isinstance(v, dict)}

        actuators = []
        for a in device.actuators:
            if not a.is_active:
                continue
            actuators.append({
                "id": a.id,
                "type": a.type,
                "pin": a.pin,
                "port": a.port,
                "state": a.current_state,
                "manual": a.manual_state,   # true / false / null(auto)
                "schedules": [
                    {
                        "start": _hhmm(s.start_time),
                        "end": _hhmm(s.end_time),
                        "days": s.repeat_days,
                        "on_min": s.interval_on_min,
                        "off_min": s.interval_off_min,
                    }
                    for s in a.schedules if s.is_active
                ],
            })

        return {
            "id": device.id,
            "device_id": device.device_id,
            "active": device.is_active,
            "thresholds": thresholds,
            "actuators": actuators,
        }


device_config_service = DeviceConfigService()