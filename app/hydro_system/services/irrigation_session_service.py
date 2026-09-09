# app/hydro_system/services/irrigation_session_service.py
#
# Session layer above raw HydroFlowReading telemetry. Follows the same
# service pattern as flow_reading_service.py / actuator_service.py.

from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.hydro_system.models.irrigation import (
    IrrigationSession,
    IrrigationSessionStatus,
)
from app.hydro_system.models.flow_reading import HydroFlowReading
from app.hydro_system.schemas.irrigation import IrrigationSessionStart
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class IrrigationSessionService:

    def start_session(self, db: Session, data: IrrigationSessionStart) -> IrrigationSession:
        """
        Idempotent start: if a session is already running for this actuator,
        return it instead of creating a duplicate.
        """
        existing = self.get_running_session_for_actuator(db, data.actuator_id)
        if existing:
            logger.info(f"[Irrigation] Session already running for actuator {data.actuator_id} (id={existing.id})")
            return existing

        try:
            session = IrrigationSession(
                actuator_id=data.actuator_id,
                device_id=data.device_id,
                zone_id=data.zone_id or data.device_id,
                target_volume_liters=data.target_volume_liters,
                trigger_type=data.trigger_type.value,
                status=IrrigationSessionStatus.running,
                start_time=datetime.now(timezone.utc),
                actual_volume_liters=0.0,
            )
            db.add(session)
            db.commit()
            db.refresh(session)
            logger.info(f"[Irrigation] Started session {session.id} for actuator {data.actuator_id}")
            return session
        except SQLAlchemyError:
            db.rollback()
            raise

    def get_session(self, db: Session, session_id: int) -> Optional[IrrigationSession]:
        return db.query(IrrigationSession).filter(IrrigationSession.id == session_id).first()

    def get_running_session_for_actuator(self, db: Session, actuator_id: int) -> Optional[IrrigationSession]:
        return (
            db.query(IrrigationSession)
            .filter(
                IrrigationSession.actuator_id == actuator_id,
                IrrigationSession.status == IrrigationSessionStatus.running,
            )
            .first()
        )

    def stop_session(
        self,
        db: Session,
        session_id: int,
        status: IrrigationSessionStatus = IrrigationSessionStatus.completed,
    ) -> Optional[IrrigationSession]:
        """
        Idempotent stop: calling this again on an already-stopped session is a
        no-op that just returns the existing (already-final) record.
        """
        session = self.get_session(db, session_id)
        if not session:
            return None

        if session.status != IrrigationSessionStatus.running:
            return session

        try:
            self._finalize_session(db, session, status)
            db.commit()
            db.refresh(session)
            logger.info(
                f"[Irrigation] Stopped session {session.id}: "
                f"{session.actual_volume_liters}L over {session.duration_seconds}s"
            )
            return session
        except SQLAlchemyError:
            db.rollback()
            raise

    def _finalize_session(self, db: Session, session: IrrigationSession, status: IrrigationSessionStatus) -> None:
        readings = (
            db.query(HydroFlowReading)
            .filter(
                HydroFlowReading.actuator_id == session.actuator_id,
                HydroFlowReading.created_at >= session.start_time,
            )
            .order_by(HydroFlowReading.created_at.asc())
            .all()
        )

        now = datetime.now(timezone.utc)
        start = session.start_time
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

        session.end_time = now
        session.duration_seconds = max((now - start).total_seconds(), 0.0)

        if readings:
            flows = [r.flow_rate for r in readings if r.flow_rate is not None]
            session.average_flow_lpm = round(sum(flows) / len(flows), 3) if flows else 0.0
            session.max_flow_lpm = round(max(flows), 3) if flows else 0.0

            if len(readings) > 1:
                # Trapezoidal integration of flow_rate (L/min) over elapsed minutes
                total = 0.0
                for prev, curr in zip(readings, readings[1:]):
                    dt_minutes = (curr.created_at - prev.created_at).total_seconds() / 60.0
                    if dt_minutes <= 0:
                        continue
                    avg_flow = (prev.flow_rate + curr.flow_rate) / 2.0
                    total += avg_flow * dt_minutes
                session.actual_volume_liters = round(total, 3)
            else:
                minutes = session.duration_seconds / 60.0
                session.actual_volume_liters = round((session.average_flow_lpm or 0.0) * minutes, 3)
        else:
            session.average_flow_lpm = 0.0
            session.max_flow_lpm = 0.0
            session.actual_volume_liters = 0.0

        session.status = status

    def list_sessions(
        self,
        db: Session,
        device_id: Optional[int] = None,
        zone_id: Optional[int] = None,
        actuator_id: Optional[int] = None,
        status: Optional[IrrigationSessionStatus] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[IrrigationSession], int]:
        query = db.query(IrrigationSession)

        if device_id:
            query = query.filter(IrrigationSession.device_id == device_id)
        if zone_id:
            query = query.filter(IrrigationSession.zone_id == zone_id)
        if actuator_id:
            query = query.filter(IrrigationSession.actuator_id == actuator_id)
        if status:
            query = query.filter(IrrigationSession.status == status)
        if start_date:
            query = query.filter(IrrigationSession.start_time >= start_date)
        if end_date:
            query = query.filter(IrrigationSession.start_time <= end_date)

        total = query.count()
        sessions = (
            query.order_by(IrrigationSession.start_time.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return sessions, total


irrigation_session_service = IrrigationSessionService()
