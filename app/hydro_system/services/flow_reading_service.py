# app/hydro_system/services/flow_reading_service.py
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.hydro_system.models.flow_reading import HydroFlowReading
from app.hydro_system.models.actuator import HydroActuator
from app.hydro_system.models.device import HydroDevice
from app.hydro_system.schemas.flow_reading import FlowReadingCreate


class FlowReadingService:

    def create_reading(self, db: Session, data: FlowReadingCreate) -> HydroFlowReading:
        actuator = db.query(HydroActuator).filter(HydroActuator.id == data.actuator_id).first()
        if not actuator:
            raise ValueError(f"Actuator {data.actuator_id} not found")

        reading = HydroFlowReading(
            actuator_id=actuator.id,
            device_id=actuator.device_id,
            flow_rate=data.flow_rate,
        )
        db.add(reading)
        db.commit()
        db.refresh(reading)
        return reading

    def get_latest_for_actuator(self, db: Session, actuator_id: int) -> Optional[HydroFlowReading]:
        return (
            db.query(HydroFlowReading)
            .filter(HydroFlowReading.actuator_id == actuator_id)
            .order_by(HydroFlowReading.created_at.desc())
            .first()
        )

    def get_latest_map_for_actuators(self, db: Session, actuator_ids: List[int]) -> Dict[int, float]:
        """
        Returns {actuator_id: latest_flow_rate} for a batch of actuators in one query
        (avoids N+1 when the automation loop checks every pump on a device).
        """
        if not actuator_ids:
            return {}

        # Subquery: latest created_at per actuator_id
        latest_ids = (
            db.query(
                HydroFlowReading.actuator_id,
                func.max(HydroFlowReading.id).label("max_id"),
            )
            .filter(HydroFlowReading.actuator_id.in_(actuator_ids))
            .group_by(HydroFlowReading.actuator_id)
            .subquery()
        )

        rows = (
            db.query(HydroFlowReading)
            .join(latest_ids, HydroFlowReading.id == latest_ids.c.max_id)
            .all()
        )
        return {r.actuator_id: r.flow_rate for r in rows}

    def get_latest_for_device(self, db: Session, device_id: int) -> List[HydroFlowReading]:
        """Latest reading per actuator, for every pump/actuator on this device."""
        actuator_ids = [
            a.id for a in db.query(HydroActuator.id).filter(HydroActuator.device_id == device_id).all()
        ]
        flow_map = self.get_latest_map_for_actuators(db, [a for (a,) in actuator_ids] if actuator_ids and isinstance(actuator_ids[0], tuple) else actuator_ids)
        return flow_map

    def get_latest_for_location(self, db: Session, location: str) -> Dict[int, float]:
        """Latest reading per actuator, across every device at a location."""
        device_ids = [
            d.id for d in db.query(HydroDevice.id).filter(HydroDevice.location == location).all()
        ]
        if not device_ids:
            return {}
        actuator_ids = [
            a.id for a in db.query(HydroActuator.id).filter(HydroActuator.device_id.in_(device_ids)).all()
        ]
        return self.get_latest_map_for_actuators(db, actuator_ids)

    def get_history_for_actuator(self, db: Session, actuator_id: int, limit: int = 100) -> List[HydroFlowReading]:
        return (
            db.query(HydroFlowReading)
            .filter(HydroFlowReading.actuator_id == actuator_id)
            .order_by(HydroFlowReading.created_at.desc())
            .limit(limit)
            .all()
        )


flow_reading_service = FlowReadingService()