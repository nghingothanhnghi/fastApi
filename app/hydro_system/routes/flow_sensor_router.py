# app/hydro_system/routes/flow_sensor_router.py
# Statistics endpoint for existing flow sensors (HydroActuator + HydroFlowReading).
# Kept separate from flow_reading_router.py so the existing /hydro/flow-readings
# endpoints are untouched (backward compatible, no breaking changes).

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.hydro_system.services.flow_reading_service import flow_reading_service
from app.hydro_system.services.water_efficiency_service import water_efficiency_service
from app.hydro_system.schemas.irrigation import FlowSensorStatisticsResponse

router = APIRouter(prefix="/flow-sensors", tags=["Hydro - Flow Sensor Statistics"])


@router.get("/{sensor_id}/statistics", response_model=FlowSensorStatisticsResponse)
def get_flow_sensor_statistics(
    sensor_id: int,
    range: Optional[str] = Query("7d", description="today | 7d | 30d (ignored if start_date/end_date given)"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
):
    start, end = water_efficiency_service.resolve_range(range, start_date, end_date)
    return flow_reading_service.get_statistics(db, sensor_id, start, end)
