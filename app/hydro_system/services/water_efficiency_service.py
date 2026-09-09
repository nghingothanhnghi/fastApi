# app/hydro_system/services/water_efficiency_service.py
#
# Turns completed IrrigationSession rows into the frontend-friendly analytics
# shape (water_usage / efficiency / statistics), compares against the
# configurable ZoneBaselineSettings, and raises deduplicated
# WaterEfficiencyAlert rows when usage exceeds the configured threshold.
#
# Layering (per spec):
#   FlowSensorService (flow_reading_service)
#       -> IrrigationSessionService
#           -> WaterEfficiencyService (this file)
#               -> BaselineService

from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.hydro_system.models.irrigation import (
    IrrigationSession,
    IrrigationSessionStatus,
    WaterEfficiencyAlert,
)
from app.hydro_system.services.baseline_service import baseline_service
from app.core.logging_config import get_logger

logger = get_logger(__name__)

VALID_RANGE_KEYS = {"today", "7d", "30d"}


class WaterEfficiencyService:

    # ── Date-range resolution ────────────────────────────────────────────

    def resolve_range(
        self,
        range_key: Optional[str],
        start_date: Optional[datetime],
        end_date: Optional[datetime],
    ) -> tuple[datetime, datetime]:
        """
        Custom start/end always wins. Otherwise resolve a named range key.
        Falls back to the last 7 days for an unrecognized/omitted key.
        """
        if start_date and end_date:
            return start_date, end_date

        now = datetime.now(timezone.utc)
        if range_key == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return start, now
        if range_key == "30d":
            return now - timedelta(days=30), now
        return now - timedelta(days=7), now

    # ── Raw statistics ───────────────────────────────────────────────────

    def get_statistics(
        self,
        db: Session,
        zone_id: Optional[int] = None,
        device_id: Optional[int] = None,
        actuator_id: Optional[int] = None,
        range_key: Optional[str] = "7d",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        start, end = self.resolve_range(range_key, start_date, end_date)

        query = db.query(IrrigationSession).filter(
            IrrigationSession.start_time >= start,
            IrrigationSession.start_time <= end,
            IrrigationSession.status == IrrigationSessionStatus.completed,
        )
        if zone_id:
            query = query.filter(IrrigationSession.zone_id == zone_id)
        if device_id:
            query = query.filter(IrrigationSession.device_id == device_id)
        if actuator_id:
            query = query.filter(IrrigationSession.actuator_id == actuator_id)

        sessions = query.all()
        session_count = len(sessions)

        total_liters = sum(s.actual_volume_liters or 0.0 for s in sessions)
        avg_flow = (
            sum(s.average_flow_lpm or 0.0 for s in sessions) / session_count
            if session_count else 0.0
        )
        avg_session_liters = (total_liters / session_count) if session_count else 0.0

        return {
            "sessions": session_count,
            "average_flow_lpm": round(avg_flow, 3),
            "average_session_liters": round(avg_session_liters, 3),
            "total_liters": round(total_liters, 3),
            "period_start": start,
            "period_end": end,
        }

    # ── Baseline comparison + efficiency status ─────────────────────────

    def get_efficiency(
        self,
        db: Session,
        zone_id: int,
        range_key: Optional[str] = "7d",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        stats = self.get_statistics(
            db, zone_id=zone_id, range_key=range_key, start_date=start_date, end_date=end_date
        )
        baseline = baseline_service.get_or_create(db, zone_id)

        current_liters = stats["total_liters"]
        baseline_liters = self._pick_baseline_liters(baseline, range_key)

        saving_liters = baseline_liters - current_liters
        saving_percent = (saving_liters / baseline_liters * 100.0) if baseline_liters else 0.0
        difference_percent = (
            ((current_liters - baseline_liters) / baseline_liters) * 100.0
            if baseline_liters else 0.0
        )

        liters_per_m2 = (current_liters / baseline.area_m2) if baseline.area_m2 else None

        threshold = baseline.efficiency_threshold_percent or 20.0
        status = self._resolve_status(baseline_liters, difference_percent, threshold)

        effective_range_key = range_key if range_key in VALID_RANGE_KEYS else "custom"
        if status == "excessive":
            self._maybe_create_alert(
                db,
                zone_id=zone_id,
                range_key=effective_range_key,
                period_start=stats["period_start"],
                period_end=stats["period_end"],
                current_liters=current_liters,
                baseline_liters=baseline_liters,
                difference_percent=difference_percent,
            )

        return {
            "water_usage": {
                "current_liters": round(current_liters, 3),
                "baseline_liters": round(baseline_liters, 3),
                "saving_liters": round(saving_liters, 3),
                "saving_percent": round(saving_percent, 3),
            },
            "efficiency": {
                "liters_per_m2": round(liters_per_m2, 3) if liters_per_m2 is not None else None,
                "status": status,
                "threshold_percent": threshold,
            },
            "statistics": {
                "sessions": stats["sessions"],
                "average_flow_lpm": stats["average_flow_lpm"],
                "average_session_liters": stats["average_session_liters"],
                "total_liters": stats["total_liters"],
            },
        }

    @staticmethod
    def _pick_baseline_liters(baseline, range_key: Optional[str]) -> float:
        if range_key == "today" and baseline.baseline_daily_liters:
            return baseline.baseline_daily_liters
        if range_key == "30d" and baseline.baseline_monthly_liters:
            return baseline.baseline_monthly_liters
        if baseline.baseline_weekly_liters:
            return baseline.baseline_weekly_liters
        # Fall back to whichever baseline is configured, in priority order
        return (
            baseline.baseline_weekly_liters
            or baseline.baseline_monthly_liters
            or baseline.baseline_daily_liters
            or 0.0
        )

    @staticmethod
    def _resolve_status(baseline_liters: float, difference_percent: float, threshold: float) -> str:
        if not baseline_liters:
            return "normal"
        if difference_percent > threshold:
            return "excessive"
        if difference_percent < -threshold:
            return "efficient"
        return "normal"

    # ── Alerting (idempotent / duplicate-safe) ──────────────────────────

    def _maybe_create_alert(
        self,
        db: Session,
        zone_id: int,
        range_key: str,
        period_start: datetime,
        period_end: datetime,
        current_liters: float,
        baseline_liters: float,
        difference_percent: float,
    ) -> Optional[WaterEfficiencyAlert]:
        existing = (
            db.query(WaterEfficiencyAlert)
            .filter(
                WaterEfficiencyAlert.zone_id == zone_id,
                WaterEfficiencyAlert.period_type == range_key,
                WaterEfficiencyAlert.period_start == period_start,
            )
            .first()
        )
        if existing:
            return existing

        alert = WaterEfficiencyAlert(
            zone_id=zone_id,
            period_type=range_key,
            period_start=period_start,
            period_end=period_end,
            current_liters=current_liters,
            baseline_liters=baseline_liters,
            difference_percent=difference_percent,
            status="excessive",
        )
        try:
            db.add(alert)
            db.commit()
            db.refresh(alert)
            logger.warning(
                f"[WaterEfficiency] Excessive usage alert: zone={zone_id} "
                f"current={current_liters}L baseline={baseline_liters}L "
                f"diff={difference_percent:.1f}%"
            )
            return alert
        except SQLAlchemyError:
            # Unique constraint race (two concurrent requests for the same
            # period) — treat as already-alerted rather than failing the request.
            db.rollback()
            return (
                db.query(WaterEfficiencyAlert)
                .filter(
                    WaterEfficiencyAlert.zone_id == zone_id,
                    WaterEfficiencyAlert.period_type == range_key,
                    WaterEfficiencyAlert.period_start == period_start,
                )
                .first()
            )


water_efficiency_service = WaterEfficiencyService()
