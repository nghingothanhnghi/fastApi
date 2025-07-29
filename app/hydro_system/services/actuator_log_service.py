# app/hydro_system/services/actuator_log_service.py
from sqlalchemy.orm import Session
from app.hydro_system.models.actuator_log import HydroActuatorLog
from app.hydro_system.models.actuator import HydroActuator
from datetime import datetime
from typing import Optional, List

def log_actuator_action(
    db: Session,
    actuator_id: int,
    action: str,
    state: str = None,
    source: str = "user",
    note: str = None
):
    log = HydroActuatorLog(
        actuator_id=actuator_id,
        action=action,
        state=state,
        source=source,
        note=note
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log

def get_actuator_logs(
    db: Session,
    actuator_id: Optional[int] = None,
    device_id: Optional[str] = None,
    client_id: Optional[int] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> List[HydroActuatorLog]:
    query = db.query(HydroActuatorLog).join(HydroActuator)

    if actuator_id:
        query = query.filter(HydroActuatorLog.actuator_id == actuator_id)

    if device_id:
        query = query.filter(HydroActuator.device_id == device_id)

    if client_id:
        query = query.join(HydroActuator.device).filter(HydroActuator.device.client_id == client_id)

    if start_time:
        query = query.filter(HydroActuatorLog.timestamp >= start_time)
    if end_time:
        query = query.filter(HydroActuatorLog.timestamp <= end_time)

    return query.order_by(HydroActuatorLog.timestamp.desc()).all()
