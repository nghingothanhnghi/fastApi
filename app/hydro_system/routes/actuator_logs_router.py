# app/hydro_system/routes/actuator_logs_router.py
# API endpoint to Logs any changes made to an actuator (pupms, valves, etc.)

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.utils.token import get_current_user
from app.user.models.user import User
from app.hydro_system.schemas.actuator_log import HydroActuatorLogOut
from app.hydro_system.services.actuator_log_service import get_actuator_logs

actuator_log_router = APIRouter()

@actuator_log_router.get("/", response_model=List[HydroActuatorLogOut])
def fetch_actuator_logs(
    actuator_id: Optional[int] = Query(None, description="Filter by actuator ID"),
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    start_time: Optional[datetime] = Query(None, description="Start timestamp (ISO format)"),
    end_time: Optional[datetime] = Query(None, description="End timestamp (ISO format)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve actuator logs. If no device_id or actuator_id is given,
    return logs for all devices belonging to the user's client.
    """
    logs = get_actuator_logs(
        db=db,
        actuator_id=actuator_id,
        device_id=device_id,
        client_id=current_user.client_id,
        start_time=start_time,
        end_time=end_time
    )
    return logs
