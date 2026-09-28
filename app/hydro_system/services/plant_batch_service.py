# app/hydro_system/services/plant_batch_service.py
#
# Multi-plan support:
#   A Plant can have several GrowthPlans, each owning its own GrowthStage
#   timeline. PlantBatch.plan_id says which plan a batch follows; all
#   stage-progression lookups are scoped by plan_id (never plant_id).

from sqlalchemy.orm import Session, joinedload
from datetime import date
from typing import List, Optional

from app.hydro_system.models.plant_batch import PlantBatch
from app.hydro_system.models.growth_stage import GrowthStage
from app.hydro_system.schemas.batch import BatchCreate, BatchDetail
from app.hydro_system.services.growth_recipe_service import growth_recipe_service
from app.hydro_system.services.growth_plan_service import growth_plan_service
from app.hydro_system.services.schedule_service import hydro_schedule_service
from app.hydro_system.services.recipe_engine_service import (
    recipe_engine_service,
    SCHEDULE_SOURCE_PLANT_AUTO,
)
from app.hydro_system.helpers.schedule_helper import get_local_today
from app.hydro_system.config import ACTIVE_BATCH_STATUSES
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Statuses set manually by a user; automatic progression must never overwrite them.
TERMINAL_STATUSES = {"harvested", "failed"}

class PlantBatchService:

    # ──────────────────────────────────────────────────────────────────────────
    # Validation helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _validate_batch(
        self,
        db: Session,
        plant_id: int,
        plan_id: Optional[int],
        zone_id: Optional[int],
        status: str,
        exclude_id: Optional[int] = None,
    ) -> None:
        """Raises ValueError on inconsistent plant/plan or a second active batch on a zone."""
        if plan_id:
            plan = growth_plan_service.get_plan(db, plan_id)
            if not plan:
                raise ValueError(f"Growth plan {plan_id} not found")
            if plan.plant_id != plant_id:
                raise ValueError("Growth plan does not belong to this plant")

        # Schedules are keyed by device (plant_auto per zone), so two active
        # batches on the same zone would overwrite each other's schedules.
        if zone_id and status in ACTIVE_BATCH_STATUSES:
            q = db.query(PlantBatch.id).filter(
                PlantBatch.zone_id == zone_id,
                PlantBatch.status.in_(ACTIVE_BATCH_STATUSES),
            )
            if exclude_id:
                q = q.filter(PlantBatch.id != exclude_id)
            if q.first():
                raise ValueError(f"Zone {zone_id} already has an active batch")

    @staticmethod
    def _clear_auto_schedules(db: Session, zone_id: Optional[int]) -> None:
        if zone_id:
            hydro_schedule_service.delete_by_device_and_source(
                db=db, device_id=zone_id, source=SCHEDULE_SOURCE_PLANT_AUTO
            )

    # ──────────────────────────────────────────────────────────────────────────
    # CRUD
    # ──────────────────────────────────────────────────────────────────────────

    def create_batch(self, db: Session, batch_in: BatchCreate) -> PlantBatch:
        """Raises ValueError (route -> 400) on invalid input."""
        data = batch_in.dict()

        if not data.get("plan_id"):
            default_plan = growth_plan_service.get_default_plan_for_plant(
                db, data["plant_id"]
            )
            if not default_plan:
                raise ValueError(
                    "This plant has no growth plan. Create a plan first."
                )
            data["plan_id"] = default_plan.id

        self._validate_batch(
            db,
            plant_id=data["plant_id"],
            plan_id=data["plan_id"],
            zone_id=data.get("zone_id"),
            status="growing",
        )

        batch = PlantBatch(**data)
        db.add(batch)
        db.commit()
        db.refresh(batch)
        return batch

    def get_batch(self, db: Session, batch_id: int) -> Optional[PlantBatch]:
        return db.query(PlantBatch).filter(PlantBatch.id == batch_id).first()

    def get_all_batches(self, db: Session) -> List[PlantBatch]:
        return db.query(PlantBatch).all()

    def update_batch(
        self, db: Session, batch_id: int, updates: dict
    ) -> Optional[PlantBatch]:
        """Raises ValueError (route -> 400) on invalid input."""
        batch = self.get_batch(db, batch_id)
        if not batch:
            return None

        new_plant = updates.get("plant_id", batch.plant_id)
        new_zone = updates.get("zone_id", batch.zone_id)
        new_status = updates.get("status", batch.status)

        # Plant changed but no explicit plan -> use the new plant's default plan
        if new_plant != batch.plant_id and "plan_id" not in updates:
            default_plan = growth_plan_service.get_default_plan_for_plant(db, new_plant)
            if not default_plan:
                raise ValueError("The new plant has no growth plan")
            updates["plan_id"] = default_plan.id
        new_plan = updates.get("plan_id", batch.plan_id)

        self._validate_batch(
            db, new_plant, new_plan, new_zone, new_status, exclude_id=batch.id
        )

        plan_changed = new_plan != batch.plan_id
        zone_changed = new_zone != batch.zone_id
        old_zone = batch.zone_id

        # Schedules generated for the old plan/zone (or a finished batch) must go
        if old_zone and (plan_changed or zone_changed or new_status in TERMINAL_STATUSES):
            self._clear_auto_schedules(db, old_zone)

        for key, value in updates.items():
            setattr(batch, key, value)

        # Force progression to re-resolve the stage and re-apply recipes
        if plan_changed or zone_changed:
            batch.current_stage_id = None

        db.commit()
        db.refresh(batch)
        return batch

    def delete_batch(self, db: Session, batch_id: int) -> bool:
        batch = self.get_batch(db, batch_id)
        if not batch:
            return False
        self._clear_auto_schedules(db, batch.zone_id)
        db.delete(batch)
        db.commit()
        return True

    # ──────────────────────────────────────────────────────────────────────────
    # Detail / enriched views
    # ──────────────────────────────────────────────────────────────────────────

    def _map_to_detail(self, batch: PlantBatch) -> BatchDetail:
        return BatchDetail(
            id=batch.id,
            plant_id=batch.plant_id,
            plan_id=batch.plan_id,
            current_stage_id=batch.current_stage_id,
            zone_id=batch.zone_id,
            start_date=batch.start_date,
            status=batch.status,
            plant_name=batch.plant.name if batch.plant else None,
            plan_name=batch.plan.name if batch.plan else None,
            current_stage_name=batch.current_stage.name if batch.current_stage else None,
            days_growing=(
                (get_local_today() - batch.start_date).days if batch.start_date else None
            ),
            device_name=batch.device.device_id if batch.device else None,
            device_location=batch.device.location if batch.device else None,
        )

    def get_all_batches_detail(self, db: Session) -> List[BatchDetail]:
        batches = (
            db.query(PlantBatch)
            .options(
                joinedload(PlantBatch.plant),
                joinedload(PlantBatch.plan),
                joinedload(PlantBatch.current_stage),
                joinedload(PlantBatch.device),
            )
            .all()
        )

        # Stages grouped by plan_id: plans of the same plant can have
        # overlapping day ranges, so progression is scoped to the batch's plan.
        stages_by_plan: dict[int, list] = {}
        for stage in (
            db.query(GrowthStage).order_by(GrowthStage.day_start.asc()).all()
        ):
            if stage.plan_id:
                stages_by_plan.setdefault(stage.plan_id, []).append(stage)

        for batch in batches:
            self.update_growth_progress(
                db, batch, stages_by_plan.get(batch.plan_id, [])
            )

        db.commit()

        for batch in batches:
            db.refresh(batch, attribute_names=["current_stage"])

        return [self._map_to_detail(b) for b in batches]

    def get_batch_detail(self, db: Session, batch_id: int) -> Optional[BatchDetail]:
        batch = (
            db.query(PlantBatch)
            .options(
                joinedload(PlantBatch.plant),
                joinedload(PlantBatch.plan),
                joinedload(PlantBatch.current_stage),
                joinedload(PlantBatch.device),
            )
            .filter(PlantBatch.id == batch_id)
            .first()
        )
        if not batch:
            return None

        # Guard: plan_id None would become "IS NULL" and match legacy stages
        # from every plant.
        stages: list[GrowthStage] = []
        if batch.plan_id:
            stages = (
                db.query(GrowthStage)
                .filter(GrowthStage.plan_id == batch.plan_id)
                .order_by(GrowthStage.day_start.asc())
                .all()
            )

        self.update_growth_progress(db, batch, stages)
        db.commit()
        db.refresh(batch, attribute_names=["current_stage"])
        return self._map_to_detail(batch)

    # ──────────────────────────────────────────────────────────────────────────
    # Growth progression logic
    # ──────────────────────────────────────────────────────────────────────────

    def update_growth_progress(
        self,
        db: Session,
        batch: PlantBatch,
        stages: list[GrowthStage],
    ) -> PlantBatch:
        """
        Recomputes stage/status from elapsed days and keeps plant_auto
        schedules in sync. Never commits (caller owns the transaction).
        """
        # Never touch manually finished batches, or batches with no plan
        # (legacy / not yet migrated: leave them exactly as they are).
        if (
            not batch.start_date
            or not batch.plan_id
            or batch.status in TERMINAL_STATUSES
        ):
            return batch

        old_stage_id = batch.current_stage_id
        old_status = batch.status

        # Plan has no stages: don't leave the old stage / schedules running.
        if not stages:
            if old_stage_id is not None:
                batch.current_stage_id = None
                self._clear_auto_schedules(db, batch.zone_id)
            return batch

        days = (get_local_today() - batch.start_date).days
        new_stage_id, new_status = self._resolve_stage_and_status(days, stages)

        stage_changed = old_stage_id != new_stage_id

        if stage_changed or old_status != new_status:
            batch.current_stage_id = new_stage_id
            batch.status = new_status

        # Stage changed: ALWAYS re-apply. apply_stage_recipes deletes the old
        # plant_auto schedules first, so an empty recipe list (or no stage)
        # correctly leaves the zone with no stale schedules.
        if stage_changed:
            recipes = (
                growth_recipe_service.get_recipes_by_stage(db, new_stage_id)
                if new_stage_id
                else []
            )
            recipe_engine_service.apply_stage_recipes(
                db=db, batch=batch, recipes=recipes
            )

        # Batch just left the active lifecycle (e.g. -> completed): clear schedules.
        if old_status in ACTIVE_BATCH_STATUSES and new_status not in ACTIVE_BATCH_STATUSES:
            self._clear_auto_schedules(db, batch.zone_id)
            logger.info(
                f"[Batch] {batch.id} {old_status} -> {new_status}; "
                f"cleared plant_auto schedules for device={batch.zone_id}"
            )

        return batch

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_stage_and_status(
        days: int,
        stages: list[GrowthStage],
    ) -> tuple[Optional[int], str]:
        """
        Pure function — no DB access.
        Returns (new_stage_id, new_status) based on elapsed days.
        `stages` must be ordered by day_start ascending.
        """
        # Before first stage starts
        if days < stages[0].day_start:
            return None, "seeded"

        # Find the active stage
        for i, stage in enumerate(stages):
            next_stage = stages[i + 1] if i + 1 < len(stages) else None
            in_range = stage.day_start <= days and (
                not next_stage or days < next_stage.day_start
            )
            if in_range:
                stage_name = (stage.name or "").lower()
                status = "flowering" if "flower" in stage_name else "growing"
                return stage.id, status

        # Past the last stage
        last = stages[-1]
        harvest_buffer = 3
        if days <= last.day_end + harvest_buffer:
            return last.id, "harvesting"
        return last.id, "completed"


plant_batch_service = PlantBatchService()