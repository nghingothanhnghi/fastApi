# app/ai_vision/integrations/hydro_batch_client.py
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.hydro_system.models.plant_batch import PlantBatch
from app.hydro_system.models.plant import Plant
from app.hydro_system.models.growth_stage import GrowthStage
from app.hydro_system.models.device import HydroDevice
from app.hydro_system.config import ACTIVE_BATCH_STATUSES
from app.hydro_system.helpers.schedule_helper import get_local_today


class HydroBatchClient:
    """Read-only reach into hydro_system. hydro_system never imports ai_vision.
    Every hydro-specific rule (stage switching, local date, active statuses,
    tenant owner of a zone) lives here so the rest of ai_vision stays
    ignorant of hydro internals."""

    # ── devices ──────────────────────────────────────────────────────────
    def get_device(self, db: Session, device_id: int) -> Optional[Dict[str, Any]]:
        device = db.query(HydroDevice).filter(HydroDevice.id == device_id).first()
        if not device:
            return None
        return {
            "id": device.id,
            "name": device.name,
            "location": device.location,
            "client_id": device.client_id,
            "user_id": device.user_id,
            "is_active": device.is_active,
        }

    # ── batches ──────────────────────────────────────────────────────────
    def get_batch_with_plant(self, db: Session, batch_id: int) -> Optional[Dict[str, Any]]:
        batch = db.query(PlantBatch).filter(PlantBatch.id == batch_id).first()
        if not batch:
            return None
        plant = db.query(Plant).filter(Plant.id == batch.plant_id).first()
        zone = (
            db.query(HydroDevice).filter(HydroDevice.id == batch.zone_id).first()
            if batch.zone_id else None
        )
        return {
            "batch_id": batch.id,
            "plant_id": batch.plant_id,
            "plan_id": batch.plan_id,
            "species": plant.name if plant else "Unknown",
            "zone_id": batch.zone_id,  # == HydroDevice.id
            "status": batch.status,
            # Owner of the zone = tenant owner of the batch (batches have no
            # client_id of their own).
            "zone_location": zone.location if zone else None,
            "zone_client_id": zone.client_id if zone else None,
            "zone_user_id": zone.user_id if zone else None,
        }

    def get_batch_growth_timeline(self, db: Session, batch_id: int) -> Optional[Dict[str, Any]]:
        """
        Batch timing + stage window, scoped by the batch's growth PLAN.

        Transition rule mirrors plant_batch_service._resolve_stage_and_status:
        a stage stays active while days < next_stage.day_start, so the
        transition happens ON next_stage.day_start. For the last stage the
        lifecycle changes (-> harvesting) at day_end + 1.
        """
        batch = db.query(PlantBatch).filter(PlantBatch.id == batch_id).first()
        if not batch:
            return None

        stages = []
        if batch.plan_id:
            stages = (
                db.query(GrowthStage)
                .filter(GrowthStage.plan_id == batch.plan_id)
                .order_by(GrowthStage.day_start.asc())
                .all()
            )

        current_stage = None
        next_stage = None
        for i, s in enumerate(stages):
            if s.id == batch.current_stage_id:
                current_stage = s
                next_stage = stages[i + 1] if i + 1 < len(stages) else None
                break

        transition_day = None
        if current_stage:
            transition_day = next_stage.day_start if next_stage else current_stage.day_end + 1

        # Same "today" as hydro (Asia/Ho_Chi_Minh), not UTC.
        days_growing = (get_local_today() - batch.start_date).days if batch.start_date else None
        days_until = (
            max(transition_day - days_growing, 0)
            if transition_day is not None and days_growing is not None
            else None
        )

        return {
            "batch_id": batch.id,
            "plan_id": batch.plan_id,
            "start_date": batch.start_date,
            "status": batch.status,
            "is_active": batch.status in ACTIVE_BATCH_STATUSES,
            "current_stage_id": current_stage.id if current_stage else None,
            "current_stage_name": current_stage.name if current_stage else None,
            "current_stage_day_end": current_stage.day_end if current_stage else None,
            "next_stage_day_start": next_stage.day_start if next_stage else None,
            "scheduled_transition_day": transition_day,
            "days_growing": days_growing,
            "days_until_scheduled_transition": days_until,
        }


hydro_batch_client = HydroBatchClient()