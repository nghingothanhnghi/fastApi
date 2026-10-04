# app/ai_vision/integrations/hydroponic_client.py
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.hydro_system.models.sensor_data import SensorData
from app.hydro_system.models.device import HydroDevice
from app.hydro_system.models.plant_batch import PlantBatch
from app.hydro_system.models.flow_reading import HydroFlowReading
from app.hydro_system.models.irrigation import (
    IrrigationSession, IrrigationSessionStatus, WaterEfficiencyAlert,
)
from app.hydro_system.services.threshold_service import threshold_service
from app.hydro_system.config import DEFAULT_THRESHOLDS
from app.ai_vision.integrations.hydro_batch_client import hydro_batch_client
from app.ai_vision import config
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# (sensor_field, min_threshold_key, max_threshold_key, human label)
_THRESHOLD_CHECKS = [
    ("ec", "ec_min", "ec_max", "EC"),
    ("ppm", "ppm_min", "ppm_max", "PPM"),
    ("moisture", "moisture_min", None, "soil moisture"),
    ("temperature", None, "temperature_max", "temperature"),
    ("light", "light_min", None, "light intensity"),
    ("water_level", "water_level_min", None, "water level"),
    # same default as hydro rules_engine.is_flow_low()
    ("flow_rate", "flow_min", None, "pump flow"),
]
_DEFAULT_FLOW_MIN = 0.5
_STALE_FACTOR = 3  # accept a reading up to 3x the window old if the window is empty


class SensorFusionService:
    """
    Reuses hydro_system's sensor / flow / irrigation data - duplicates none of it.

    Device resolution (most reliable first):
        1. PlantBatch.zone_id   (hydro's own plant -> device link)
        2. VisionCamera.hydro_device_id
        3. VisionPlant.location, scoped to the plant's client_id

    If no device can be resolved we return {} rather than averaging every
    device's data (the old behaviour when location was None).
    """

    # ── helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _to_naive_utc(ts: Optional[datetime]) -> datetime:
        """SensorData.created_at is naive UTC; captured_at may be aware."""
        if ts is None:
            return datetime.utcnow()
        if ts.tzinfo is not None:
            return ts.astimezone(timezone.utc).replace(tzinfo=None)
        return ts

    def resolve_device(self, db: Session, plant) -> Optional[HydroDevice]:
        device_id = None
        if plant.hydro_batch_id:
            row = db.query(PlantBatch.zone_id).filter(PlantBatch.id == plant.hydro_batch_id).first()
            device_id = row[0] if row else None
        if device_id is None and plant.camera is not None:
            device_id = plant.camera.hydro_device_id
        if device_id is not None:
            return db.query(HydroDevice).filter(HydroDevice.id == device_id).first()

        if plant.location:
            q = db.query(HydroDevice).filter(
                HydroDevice.location == plant.location,
                HydroDevice.is_active == True,  # noqa: E712
            )
            if plant.client_id:
                q = q.filter(HydroDevice.client_id == plant.client_id)  # never cross tenants
            return q.order_by(HydroDevice.id.asc()).first()
        return None

    # ── main entry ───────────────────────────────────────────────────────
    def get_window(self, db: Session, plant, timestamp: Optional[datetime]) -> Dict[str, Any]:
        """Average readings in the window ending at `timestamp` for the
        plant's hydro device, plus which averages violate that device's
        own automation thresholds."""
        device = self.resolve_device(db, plant) if plant else None
        if device is None:
            logger.warning(
                "[AIVision] No hydro device resolved for plant %s (batch=%s, location=%r); "
                "skipping sensor fusion",
                getattr(plant, "id", None), getattr(plant, "hydro_batch_id", None),
                getattr(plant, "location", None),
            )
            return {}

        end = self._to_naive_utc(timestamp)
        window = timedelta(minutes=config.SENSOR_WINDOW_MINUTES)
        start = end - window

        context = self._build_context(db, plant, device)

        readings = (
            db.query(SensorData)
            .filter(
                SensorData.device_id == device.id,
                SensorData.created_at >= start,
                SensorData.created_at <= end,
            )
            .all()
        )
        stale = False
        if not readings:
            latest = (
                db.query(SensorData)
                .filter(
                    SensorData.device_id == device.id,
                    SensorData.created_at <= end,
                    SensorData.created_at >= end - window * _STALE_FACTOR,
                )
                .order_by(SensorData.created_at.desc())
                .first()
            )
            if latest:
                readings, stale = [latest], True

        if not readings:
            return {"context": context, "no_sensor_data": True}

        def avg(field):
            values = [getattr(r, field) for r in readings if getattr(r, field) is not None]
            return round(sum(values) / len(values), 2) if values else None

        rain_flags = [r.rain_detected for r in readings if r.rain_detected is not None]

        snapshot: Dict[str, Any] = {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "stale": stale,
            "temperature": avg("temperature"),
            "humidity": avg("humidity"),
            "light": avg("light"),
            "moisture": avg("moisture"),
            "water_level": avg("water_level"),
            "ec": avg("ec"),
            "ppm": avg("ppm"),
            "rain_detected": any(rain_flags) if rain_flags else None,
            "rain_intensity": avg("rain_intensity"),
            "context": context,
        }

        snapshot.update(self._flow_stats(db, device.id, start, end))
        snapshot["irrigation"] = self._irrigation_context(db, device.id, end)

        thresholds = threshold_service.get_for_device(device) or dict(DEFAULT_THRESHOLDS)
        snapshot["anomalous_sensors"] = self._flag_out_of_range(snapshot, thresholds)
        return snapshot

    # ── pieces ───────────────────────────────────────────────────────────
    @staticmethod
    def _build_context(db: Session, plant, device: HydroDevice) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {
            "device_id": device.id,
            "device_name": device.name,
            "location": device.location,
        }
        if plant.hydro_batch_id:
            timeline = hydro_batch_client.get_batch_growth_timeline(db, plant.hydro_batch_id)
            if timeline:
                ctx.update({
                    "batch_id": timeline["batch_id"],
                    "batch_status": timeline["status"],
                    "stage": timeline["current_stage_name"],
                    "days_growing": timeline["days_growing"],
                })
        return ctx

    @staticmethod
    def _flow_stats(db: Session, device_id: int, start: datetime, end: datetime) -> Dict[str, Any]:
        # created_at on flow readings is timezone-aware -> compare with aware UTC
        s = start.replace(tzinfo=timezone.utc)
        e = end.replace(tzinfo=timezone.utc)
        rows = (
            db.query(HydroFlowReading.flow_rate)
            .filter(
                HydroFlowReading.device_id == device_id,
                HydroFlowReading.created_at >= s,
                HydroFlowReading.created_at <= e,
            )
            .all()
        )
        values = [r[0] for r in rows if r[0] is not None]
        running = [v for v in values if v > 0]  # 0 L/min = pump off, not a fault
        out: Dict[str, Any] = {"flow_reading_count": len(values)}
        if running:
            out["flow_rate"] = round(sum(running) / len(running), 2)
        return out

    @staticmethod
    def _irrigation_context(db: Session, device_id: int, end: datetime) -> Dict[str, Any]:
        active = (
            db.query(IrrigationSession)
            .filter(
                IrrigationSession.device_id == device_id,
                IrrigationSession.status == IrrigationSessionStatus.running,
            )
            .count()
        )
        cutoff = end.replace(tzinfo=timezone.utc) - timedelta(days=7)
        alert = (
            db.query(WaterEfficiencyAlert)
            .filter(WaterEfficiencyAlert.zone_id == device_id, WaterEfficiencyAlert.created_at >= cutoff)
            .order_by(WaterEfficiencyAlert.created_at.desc())
            .first()
        )
        return {
            "active_sessions": active,
            "excessive_usage_alert": (
                {
                    "period": alert.period_type,
                    "difference_percent": round(alert.difference_percent, 1),
                    "current_liters": alert.current_liters,
                    "baseline_liters": alert.baseline_liters,
                }
                if alert else None
            ),
        }

    @staticmethod
    def _flag_out_of_range(snapshot: Dict[str, Any], thresholds: Dict[str, Any]) -> List[Dict[str, Any]]:
        flags = []
        for field, min_key, max_key, label in _THRESHOLD_CHECKS:
            value = snapshot.get(field)
            if value is None:
                continue
            min_val = thresholds.get(min_key, _DEFAULT_FLOW_MIN if field == "flow_rate" else None) if min_key else None
            max_val = thresholds.get(max_key) if max_key else None
            if min_val is not None and value < min_val:
                flags.append({"sensor": field, "label": label, "value": value,
                              "direction": "low", "threshold": min_val})
            if max_val is not None and value > max_val:
                flags.append({"sensor": field, "label": label, "value": value,
                              "direction": "high", "threshold": max_val})
        return flags


sensor_fusion_service = SensorFusionService()