# app/hydro_system/services/plant_batch_service.py
#
# STEP 1 FIX — Circular import removed:
#   BEFORE: imported controllers/recipe_engine_controller  ❌
#   AFTER:  imports services/recipe_engine_service          ✅

from sqlalchemy.orm import Session, joinedload
from datetime import date
from typing import List, Optional

from app.hydro_system.models.plant_batch import PlantBatch
from app.hydro_system.models.growth_stage import GrowthStage
from app.hydro_system.schemas.batch import BatchCreate, BatchDetail
from app.hydro_system.services.growth_recipe_service import growth_recipe_service
# ✅ service imports service — no controller import
from app.hydro_system.services.recipe_engine_service import recipe_engine_service
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class PlantBatchService:

    def create_batch(self, db: Session, batch_in: BatchCreate) -> PlantBatch:
        batch = PlantBatch(**batch_in.dict())
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
        batch = self.get_batch(db, batch_id)
        if not batch:
            return None
        for key, value in updates.items():
            setattr(batch, key, value)
        db.commit()
        db.refresh(batch)
        return batch

    def delete_batch(self, db: Session, batch_id: int) -> bool:
        batch = self.get_batch(db, batch_id)
        if not batch:
            return False
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
            current_stage_id=batch.current_stage_id,
            zone_id=batch.zone_id,
            start_date=batch.start_date,
            status=batch.status,
            plant_name=batch.plant.name if batch.plant else None,
            current_stage_name=batch.current_stage.name if batch.current_stage else None,
            days_growing=(
                (date.today() - batch.start_date).days if batch.start_date else None
            ),
            device_name=batch.device.device_id if batch.device else None,
            device_location=batch.device.location if batch.device else None,
        )

    def get_all_batches_detail(self, db: Session) -> List[BatchDetail]:
        batches = (
            db.query(PlantBatch)
            .options(
                joinedload(PlantBatch.plant),
                joinedload(PlantBatch.current_stage),
                joinedload(PlantBatch.device),
            )
            .all()
        )

        # Load all stages in one query, grouped by plant_id
        stages_by_plant: dict[int, list] = {}
        for stage in (
            db.query(GrowthStage).order_by(GrowthStage.day_start.asc()).all()
        ):
            stages_by_plant.setdefault(stage.plant_id, []).append(stage)

        for batch in batches:
            self.update_growth_progress(
                db, batch, stages_by_plant.get(batch.plant_id, [])
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
                joinedload(PlantBatch.current_stage),
            )
            .filter(PlantBatch.id == batch_id)
            .first()
        )
        if not batch:
            return None

        stages = (
            db.query(GrowthStage)
            .filter(GrowthStage.plant_id == batch.plant_id)
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
        if not batch.start_date or not stages:
            return batch

        days = (date.today() - batch.start_date).days
        old_stage_id = batch.current_stage_id
        old_status = batch.status

        new_stage_id, new_status = self._resolve_stage_and_status(days, stages, old_status)

        stage_changed = old_stage_id != new_stage_id

        if stage_changed or old_status != new_status:
            batch.current_stage_id = new_stage_id
            batch.status = new_status

        # Apply recipes when stage advances — ✅ calls service, not controller
        if stage_changed and new_stage_id:
            recipes = growth_recipe_service.get_recipes_by_stage(db, new_stage_id)
            if recipes:
                recipe_engine_service.apply_stage_recipes(
                    db=db, batch=batch, recipes=recipes
                )

        return batch

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_stage_and_status(
        days: int,
        stages: list[GrowthStage],
        current_status: str,
    ) -> tuple[Optional[int], str]:
        """
        Pure function — no DB access.
        Returns (new_stage_id, new_status) based on elapsed days.
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
