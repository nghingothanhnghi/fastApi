# app/hydro_system/routes/irrigation_router.py
# Routes only handle HTTP concerns — all business logic lives in the
# irrigation_session_service / water_efficiency_service / baseline_service.

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.hydro_system.schemas.irrigation import (
    IrrigationSessionStart,
    IrrigationSessionStop,
    IrrigationSessionOut,
    PaginatedIrrigationSessions,
    ZoneBaselineUpdate,
    ZoneBaselineOut,
    IrrigationEfficiencyResponse,
    IrrigationStatisticsResponse,
    IrrigationSessionStatus,
)
from app.hydro_system.models.irrigation import IrrigationSessionStatus as ModelSessionStatus
from app.hydro_system.services.irrigation_session_service import irrigation_session_service
from app.hydro_system.services.baseline_service import baseline_service
from app.hydro_system.services.water_efficiency_service import water_efficiency_service

router = APIRouter(prefix="/irrigation", tags=["Hydro - Irrigation"])


# ── Sessions ─────────────────────────────────────────────────────────────

@router.post("/sessions/start", response_model=IrrigationSessionOut)
def start_irrigation_session(data: IrrigationSessionStart, db: Session = Depends(get_db)):
    """Idempotent: calling this again while a session is already running for
    the same actuator returns the existing session instead of duplicating it."""
    return irrigation_session_service.start_session(db, data)


@router.post("/sessions/{session_id}/stop", response_model=IrrigationSessionOut)
def stop_irrigation_session(
    session_id: int,
    data: IrrigationSessionStop = IrrigationSessionStop(),
    db: Session = Depends(get_db),
):
    """Idempotent: stopping an already-stopped session just returns it."""
    session = irrigation_session_service.stop_session(
        db, session_id, status=ModelSessionStatus(data.status.value)
    )
    if not session:
        raise HTTPException(status_code=404, detail="Irrigation session not found")
    return session


@router.get("/sessions", response_model=PaginatedIrrigationSessions)
def list_irrigation_sessions(
    device_id: Optional[int] = Query(None),
    zone_id: Optional[int] = Query(None),
    actuator_id: Optional[int] = Query(None),
    status: Optional[IrrigationSessionStatus] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    model_status = ModelSessionStatus(status.value) if status else None
    sessions, total = irrigation_session_service.list_sessions(
        db,
        device_id=device_id,
        zone_id=zone_id,
        actuator_id=actuator_id,
        status=model_status,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return {"results": sessions, "total": total, "page": page, "page_size": page_size}


@router.get("/sessions/{session_id}", response_model=IrrigationSessionOut)
def get_irrigation_session(session_id: int, db: Session = Depends(get_db)):
    session = irrigation_session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Irrigation session not found")
    return session


# ── Statistics / efficiency ─────────────────────────────────────────────

@router.get("/statistics", response_model=IrrigationStatisticsResponse)
def get_irrigation_statistics(
    zone_id: Optional[int] = Query(None),
    device_id: Optional[int] = Query(None),
    actuator_id: Optional[int] = Query(None),
    range: Optional[str] = Query("7d", description="today | 7d | 30d (ignored if start_date/end_date given)"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
):
    return water_efficiency_service.get_statistics(
        db,
        zone_id=zone_id,
        device_id=device_id,
        actuator_id=actuator_id,
        range_key=range,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/efficiency", response_model=IrrigationEfficiencyResponse)
def get_irrigation_efficiency(
    zone_id: int = Query(..., description="Zone identifier (HydroDevice.id)"),
    range: Optional[str] = Query("7d", description="today | 7d | 30d (ignored if start_date/end_date given)"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Returns the frontend-friendly water_usage/efficiency/statistics payload
    and — if usage exceeds the zone's configured threshold — raises a
    deduplicated efficiency alert as a side effect.
    """
    return water_efficiency_service.get_efficiency(
        db, zone_id=zone_id, range_key=range, start_date=start_date, end_date=end_date
    )


# ── Baseline settings ────────────────────────────────────────────────────

@router.get("/baseline", response_model=ZoneBaselineOut)
def get_zone_baseline(
    zone_id: int = Query(..., description="Zone identifier (HydroDevice.id)"),
    db: Session = Depends(get_db),
):
    return baseline_service.get_or_create(db, zone_id)


@router.put("/baseline", response_model=ZoneBaselineOut)
def update_zone_baseline(
    data: ZoneBaselineUpdate,
    zone_id: int = Query(..., description="Zone identifier (HydroDevice.id)"),
    db: Session = Depends(get_db),
):
    return baseline_service.update(db, zone_id, data)
