# app/ai_vision/integrations/hydroponic_client.py
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.hydro_system.models.sensor_data import SensorData
from app.hydro_system.models.device import HydroDevice
from app.hydro_system.services.flow_reading_service import flow_reading_service
from app.hydro_system.services.threshold_service import threshold_service
from app.hydro_system.config import DEFAULT_THRESHOLDS
from app.ai_vision import config

# (sensor_field, min_threshold_key, max_threshold_key, human label)
# min/max key of None means "no bound checked on that side" for that sensor.
_THRESHOLD_CHECKS = [
    ("ec", "ec_min", "ec_max", "EC"),
    ("ppm", "ppm_min", "ppm_max", "PPM"),
    ("moisture", "moisture_min", None, "soil moisture"),
    ("temperature", None, "temperature_max", "temperature"),
    ("light", "light_min", None, "light intensity"),
    ("water_level", "water_level_min", None, "water level"),
]


class SensorFusionService:
    """Reuses the existing hydro_system sensor/flow infrastructure - does not
    duplicate SensorData or HydroFlowReading. This is the only place the
    ai_vision module reaches into hydro_system's data layer.

    V4: get_window() now does more than average raw values - it compares
    the window's averages against the same per-device automation thresholds
    hydro_system's own rule engine uses (threshold_service), and reports
    which sensors were actually out of range in that window
    (`anomalous_sensors`). This turns the sensor snapshot from a passive
    number dump into something RecommendationService can correlate against
    a visual symptom (see recommendation_service._correlate_visual_and_sensor).
    """

    def get_window(
        self, db: Session, location: Optional[str], timestamp: datetime
    ) -> Dict[str, Any]:
        """Average sensor readings in the window ending at `timestamp`,
        for whichever hydro device matches the camera's location, plus
        which of those averages are outside that device's configured
        automation thresholds."""
        window_start = timestamp - timedelta(minutes=config.SENSOR_WINDOW_MINUTES)

        device = None
        query = db.query(SensorData).filter(
            SensorData.created_at >= window_start,
            SensorData.created_at <= timestamp,
        )
        if location:
            device = db.query(HydroDevice).filter(HydroDevice.location == location).first()
            query = query.join(HydroDevice, SensorData.device_id == HydroDevice.id).filter(
                HydroDevice.location == location
            )

        readings = query.all()
        if not readings:
            return {}

        def avg(field):
            values = [getattr(r, field) for r in readings if getattr(r, field) is not None]
            return round(sum(values) / len(values), 2) if values else None

        snapshot = {
            "window_start": window_start.isoformat(),
            "window_end": timestamp.isoformat(),
            "temperature": avg("temperature"),
            "humidity": avg("humidity"),
            "light": avg("light"),
            "moisture": avg("moisture"),
            "water_level": avg("water_level"),
            "ec": avg("ec"),
            "ppm": avg("ppm"),
        }

        device_ids = {r.device_id for r in readings if r.device_id}
        flow_rates = []
        for device_id in device_ids:
            flow_map = flow_reading_service.get_latest_for_device(db, device_id)
            flow_rates.extend(flow_map.values() if isinstance(flow_map, dict) else [])
        if flow_rates:
            snapshot["flow_rate"] = round(sum(flow_rates) / len(flow_rates), 2)

        thresholds = threshold_service.get_for_device(device) if device else dict(DEFAULT_THRESHOLDS)
        snapshot["anomalous_sensors"] = self._flag_out_of_range(snapshot, thresholds)

        return snapshot

    @staticmethod
    def _flag_out_of_range(snapshot: Dict[str, Any], thresholds: Dict[str, Any]) -> List[Dict[str, Any]]:
        flags = []
        for field, min_key, max_key, label in _THRESHOLD_CHECKS:
            value = snapshot.get(field)
            if value is None:
                continue
            if min_key and thresholds.get(min_key) is not None and value < thresholds[min_key]:
                flags.append({
                    "sensor": field, "label": label, "value": value,
                    "direction": "low", "threshold": thresholds[min_key],
                })
            if max_key and thresholds.get(max_key) is not None and value > thresholds[max_key]:
                flags.append({
                    "sensor": field, "label": label, "value": value,
                    "direction": "high", "threshold": thresholds[max_key],
                })
        return flags


sensor_fusion_service = SensorFusionService()
