# app/hydro_system/models/irrigation.py
#
# Session + analytics layer built on top of the existing HydroFlowReading
# telemetry model (app/hydro_system/models/flow_reading.py). Raw per-reading
# telemetry stays in hydro_flow_readings; this file only adds:
#   - hydro_irrigation_sessions   (aggregated session-level rollups)
#   - hydro_zone_baselines        (configurable per-zone baseline/thresholds)
#   - hydro_efficiency_alerts     (deduplicated excessive-usage events)
#
# "zone" reuses HydroDevice.id, matching the existing convention already used
# by PlantBatch.zone_id (app/hydro_system/models/plant_batch.py), so no new
# Zone table/concept is introduced.

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Enum, func,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class IrrigationSessionStatus(str, enum.Enum):
    running = "running"
    completed = "completed"
    cancelled = "cancelled"
    error = "error"


class IrrigationTriggerType(str, enum.Enum):
    manual = "manual"
    schedule = "schedule"
    automation = "automation"


class IrrigationSession(Base):
    """
    One row per irrigation run for a given actuator (pump/valve acting as the
    flow-sensored device). Aggregates the raw HydroFlowReading telemetry that
    falls within [start_time, end_time] instead of persisting a derived row
    every few seconds.
    """
    __tablename__ = "hydro_irrigation_sessions"

    id = Column(Integer, primary_key=True, index=True)

    actuator_id = Column(Integer, ForeignKey("hydro_actuators.id"), nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("devices_hydro.id"), nullable=False, index=True)
    zone_id = Column(Integer, ForeignKey("devices_hydro.id"), nullable=False, index=True)

    target_volume_liters = Column(Float, nullable=True)
    actual_volume_liters = Column(Float, nullable=False, default=0.0)

    start_time = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, nullable=True)

    average_flow_lpm = Column(Float, nullable=True)
    max_flow_lpm = Column(Float, nullable=True)

    status = Column(Enum(IrrigationSessionStatus), default=IrrigationSessionStatus.running, nullable=False, index=True)
    trigger_type = Column(Enum(IrrigationTriggerType), default=IrrigationTriggerType.manual, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    actuator = relationship("HydroActuator")
    device = relationship("HydroDevice", foreign_keys=[device_id])

    __table_args__ = (
        # Speeds up "give me sessions for this zone in this date range" queries,
        # which back both /irrigation/statistics and /irrigation/efficiency.
        Index("ix_irrigation_sessions_zone_start", "zone_id", "start_time"),
    )

    def __repr__(self):
        return f"<IrrigationSession(id={self.id}, actuator_id={self.actuator_id}, status={self.status})>"


class ZoneBaselineSettings(Base):
    """
    Configurable baseline/threshold settings, one row per zone (device).
    Never hard-code thresholds in code - this table is the source of truth
    and is editable via PUT /irrigation/baseline.
    """
    __tablename__ = "hydro_zone_baselines"

    id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("devices_hydro.id"), nullable=False, unique=True, index=True)

    area_m2 = Column(Float, nullable=True)

    baseline_daily_liters = Column(Float, nullable=True)
    baseline_weekly_liters = Column(Float, nullable=True)
    baseline_monthly_liters = Column(Float, nullable=True)
    baseline_liters_per_m2 = Column(Float, nullable=True)

    efficiency_threshold_percent = Column(Float, nullable=False, default=20.0)

    is_active = Column(Integer, nullable=False, default=1)  # simple soft-delete flag (1/0), matches project's is_active convention

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<ZoneBaselineSettings(zone_id={self.zone_id})>"


class WaterEfficiencyAlert(Base):
    """
    One row per (zone, period_type, period_start) that exceeded the
    configured efficiency threshold. The unique constraint is what makes
    alert generation idempotent/duplicate-safe (see WaterEfficiencyService).
    """
    __tablename__ = "hydro_efficiency_alerts"

    id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("devices_hydro.id"), nullable=False, index=True)

    period_type = Column(String(20), nullable=False)  # "today" | "7d" | "30d" | custom range key
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)

    current_liters = Column(Float, nullable=False)
    baseline_liters = Column(Float, nullable=False)
    difference_percent = Column(Float, nullable=False)
    status = Column(String(20), nullable=False, default="excessive")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("zone_id", "period_type", "period_start", name="uq_zone_period_alert"),
    )

    def __repr__(self):
        return f"<WaterEfficiencyAlert(zone_id={self.zone_id}, period={self.period_type}, diff%={self.difference_percent})>"
