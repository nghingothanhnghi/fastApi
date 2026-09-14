# app/ai_vision/integrations/hydroponic_client.py
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.hydro_system.models.sensor_data import SensorData
from app.hydro_system.models.device import HydroDevice
from app.hydro_system.services.flow_reading_service import flow_reading_service
from app.ai_vision import config


class SensorFusionService:
    """Reuses the existing hydro_system sensor/flow infrastructure - does not
    duplicate SensorData or HydroFlowReading. This is the only place the
    ai_vision module reaches into hydro_system's data layer."""

    def get_window(
        self, db: Session, location: Optional[str], timestamp: datetime
    ) -> Dict[str, Any]:
        """Average sensor readings in the window ending at `timestamp`,
        for whichever hydro device matches the camera's location."""
        window_start = timestamp - timedelta(minutes=config.SENSOR_WINDOW_MINUTES)

        query = db.query(SensorData).filter(
            SensorData.created_at >= window_start,
            SensorData.created_at <= timestamp,
        )
        if location:
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

        return snapshot


sensor_fusion_service = SensorFusionService()
