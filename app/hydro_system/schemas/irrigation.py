# app/hydro_system/schemas/irrigation.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class IrrigationSessionStatus(str, Enum):
    running = "running"
    completed = "completed"
    cancelled = "cancelled"
    error = "error"


class IrrigationTriggerType(str, Enum):
    manual = "manual"
    schedule = "schedule"
    automation = "automation"


# ── Sessions ────────────────────────────────────────────────────────────

class IrrigationSessionStart(BaseModel):
    actuator_id: int = Field(..., description="Pump/valve actuator this flow sensor is attached to")
    device_id: int
    zone_id: Optional[int] = Field(None, description="Defaults to device_id if omitted")
    target_volume_liters: Optional[float] = Field(None, ge=0)
    trigger_type: IrrigationTriggerType = IrrigationTriggerType.manual


class IrrigationSessionStop(BaseModel):
    status: IrrigationSessionStatus = IrrigationSessionStatus.completed


class IrrigationSessionOut(BaseModel):
    id: int
    actuator_id: int
    device_id: int
    zone_id: int
    target_volume_liters: Optional[float] = None
    actual_volume_liters: float
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    average_flow_lpm: Optional[float] = None
    max_flow_lpm: Optional[float] = None
    status: IrrigationSessionStatus
    trigger_type: IrrigationTriggerType
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PaginatedIrrigationSessions(BaseModel):
    results: List[IrrigationSessionOut]
    total: int
    page: int
    page_size: int


# ── Baseline / settings ─────────────────────────────────────────────────

class ZoneBaselineUpdate(BaseModel):
    area_m2: Optional[float] = Field(None, ge=0)
    baseline_daily_liters: Optional[float] = Field(None, ge=0)
    baseline_weekly_liters: Optional[float] = Field(None, ge=0)
    baseline_monthly_liters: Optional[float] = Field(None, ge=0)
    baseline_liters_per_m2: Optional[float] = Field(None, ge=0)
    efficiency_threshold_percent: Optional[float] = Field(None, ge=0, le=1000)


class ZoneBaselineOut(BaseModel):
    zone_id: int
    area_m2: Optional[float] = None
    baseline_daily_liters: Optional[float] = None
    baseline_weekly_liters: Optional[float] = None
    baseline_monthly_liters: Optional[float] = None
    baseline_liters_per_m2: Optional[float] = None
    efficiency_threshold_percent: float

    model_config = {"from_attributes": True}


# ── Analytics response blocks (frontend-friendly shape) ─────────────────

class WaterUsageBlock(BaseModel):
    current_liters: float
    baseline_liters: float
    saving_liters: float
    saving_percent: float


class EfficiencyBlock(BaseModel):
    liters_per_m2: Optional[float] = None
    status: str  # efficient | normal | excessive
    threshold_percent: float


class StatisticsBlock(BaseModel):
    sessions: int
    average_flow_lpm: float
    average_session_liters: float
    total_liters: float


class IrrigationEfficiencyResponse(BaseModel):
    water_usage: WaterUsageBlock
    efficiency: EfficiencyBlock
    statistics: StatisticsBlock


class IrrigationStatisticsResponse(BaseModel):
    sessions: int
    average_flow_lpm: float
    average_session_liters: float
    total_liters: float
    period_start: datetime
    period_end: datetime


class FlowSensorStatisticsResponse(BaseModel):
    sensor_id: int
    period_start: datetime
    period_end: datetime
    total_volume_liters: float
    average_flow_lpm: float
    max_flow_lpm: float
    reading_count: int
