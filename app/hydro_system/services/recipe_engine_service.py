# app/hydro_system/services/recipe_engine_service.py
#
# RULE: services -> models/schemas only. No service may import a controller.
# TRANSACTIONS: never commits; the caller owns the transaction.

from datetime import time
from typing import Dict, List, Optional
from sqlalchemy.orm import Session, joinedload

from app.hydro_system.services.actuator_service import hydro_actuator_service
from app.hydro_system.services.schedule_service import hydro_schedule_service
from app.hydro_system.models.schedule import HydroSchedule
from app.hydro_system.models.plant_batch import PlantBatch
from app.hydro_system.models.growth_stage import GrowthStage
from app.hydro_system.config import ACTIVE_BATCH_STATUSES
from app.core.logging_config import get_logger

logger = get_logger(__name__)

SCHEDULE_SOURCE_PLANT_AUTO = "plant_auto"


class RecipeEngineService:
    """
    Translates GrowthRecipe rows into HydroSchedule rows.

    Targeting (most specific wins per actuator):
        actuator_id  >  group_name  >  actuator_type only
    Recipes of equal specificity stack (e.g. two 'on' windows).
    """

    # ── specificity ──────────────────────────────────────────────────────
    @staticmethod
    def specificity(recipe) -> int:
        if getattr(recipe, "actuator_id", None):
            return 2
        if getattr(recipe, "group_name", None):
            return 1
        return 0

    # ── public API ───────────────────────────────────────────────────────
    def apply_stage_recipes(self, db: Session, batch, recipes: list) -> None:
        if batch.zone_id is None:
            logger.warning(
                f"[RecipeEngine] Batch {batch.id} has no zone_id - no schedules applied."
            )
            return

        hydro_schedule_service.delete_by_device_and_source(
            db=db, device_id=batch.zone_id, source=SCHEDULE_SOURCE_PLANT_AUTO,
        )

        # actuator_id -> highest specificity already applied to it
        claimed: Dict[int, int] = {}
        for recipe in sorted(recipes, key=self.specificity, reverse=True):
            self._apply_single_recipe(db, batch, recipe, claimed)

    def reapply_for_stage(self, db: Session, stage_id: int) -> None:
        stage = (
            db.query(GrowthStage)
            .options(joinedload(GrowthStage.recipes))
            .filter(GrowthStage.id == stage_id)
            .first()
        )
        if not stage:
            return
        batches = (
            db.query(PlantBatch)
            .filter(
                PlantBatch.current_stage_id == stage_id,
                PlantBatch.status.in_(ACTIVE_BATCH_STATUSES),
            )
            .all()
        )
        for batch in batches:
            self.apply_stage_recipes(db, batch, stage.recipes)

    def reapply_for_device(self, db: Session, device_id: int) -> None:
        batch = (
            db.query(PlantBatch)
            .options(joinedload(PlantBatch.current_stage).joinedload(GrowthStage.recipes))
            .filter(
                PlantBatch.zone_id == device_id,
                PlantBatch.status.in_(ACTIVE_BATCH_STATUSES),
            )
            .first()
        )
        if batch and batch.current_stage:
            self.apply_stage_recipes(db, batch, batch.current_stage.recipes)

    # ── target resolution ────────────────────────────────────────────────
    def resolve_targets(self, db: Session, batch, recipe) -> list:
        """Active actuators on the batch's zone that this recipe addresses."""
        if getattr(recipe, "actuator_id", None):
            actuator = hydro_actuator_service.get_actuator(db, recipe.actuator_id)
            if (
                not actuator
                or actuator.device_id != batch.zone_id
                or not actuator.is_active
                or actuator.type != recipe.actuator_type
            ):
                logger.warning(
                    f"[RecipeEngine] Recipe {recipe.id} targets actuator "
                    f"{recipe.actuator_id}, which is missing, inactive, of another "
                    f"type, or not on zone {batch.zone_id} - skipped."
                )
                return []
            return [actuator]

        actuators = hydro_actuator_service.get_active_actuators_by_type(
            db=db, actuator_type=recipe.actuator_type, device_id=batch.zone_id,
        )
        group = getattr(recipe, "group_name", None)
        if group:
            actuators = [a for a in actuators if a.group_name == group]
        return actuators

    # ── internals ────────────────────────────────────────────────────────
    def _apply_single_recipe(
        self, db: Session, batch, recipe, claimed: Optional[Dict[int, int]] = None
    ) -> None:
        if batch.zone_id is None:
            logger.warning(f"[RecipeEngine] Batch {batch.id} has no zone_id - recipe skipped.")
            return

        claimed = claimed if claimed is not None else {}
        level = self.specificity(recipe)

        targets = [
            a for a in self.resolve_targets(db, batch, recipe)
            if claimed.get(a.id, -1) <= level          # drop actuators owned by a MORE specific recipe
        ]
        if not targets:
            logger.warning(
                f"[RecipeEngine] Recipe {recipe.id} ({recipe.actuator_type}) matched no "
                f"free actuators on device {batch.zone_id} - skipped."
            )
            return

        schedules = self._build_schedules(targets, recipe)
        if not schedules:
            return   # invalid recipe: do not claim, so a broader recipe may still apply

        hydro_schedule_service.bulk_create(db, schedules, commit=False)
        for a in targets:
            claimed[a.id] = max(claimed.get(a.id, -1), level)

        logger.info(
            f"[RecipeEngine] Created {len(schedules)} schedule(s) for "
            f"'{recipe.actuator_type}' group={getattr(recipe, 'group_name', None)} "
            f"actuator_id={getattr(recipe, 'actuator_id', None)} (action={recipe.action})."
        )

    def _build_schedules(self, actuators: list, recipe) -> List[HydroSchedule]:
        if recipe.action == "on":
            return self._build_on_schedules(actuators, recipe)
        if recipe.action == "interval":
            return self._build_interval_schedules(actuators, recipe)
        logger.warning(f"[RecipeEngine] Unknown recipe action '{recipe.action}' - skipped.")
        return []

    @staticmethod
    def _build_on_schedules(actuators: list, recipe) -> List[HydroSchedule]:
        if not recipe.start_time or not recipe.end_time:
            logger.warning("[RecipeEngine] 'on' recipe missing start_time/end_time - skipped.")
            return []
        return [
            HydroSchedule(
                actuator_id=a.id,
                start_time=recipe.start_time,
                end_time=recipe.end_time,
                repeat_days="mon,tue,wed,thu,fri,sat,sun",
                is_active=True,
                source=SCHEDULE_SOURCE_PLANT_AUTO,
            )
            for a in actuators
        ]

    @staticmethod
    def _build_interval_schedules(actuators: list, recipe) -> List[HydroSchedule]:
        if not recipe.interval_on_min or not recipe.interval_off_min:
            logger.warning("[RecipeEngine] 'interval' recipe missing interval values - skipped.")
            return []
        start_time = recipe.start_time or time(0, 0)
        end_time = recipe.end_time or time(23, 59)
        return [
            HydroSchedule(
                actuator_id=a.id,
                start_time=start_time,
                end_time=end_time,
                interval_on_min=recipe.interval_on_min,
                interval_off_min=recipe.interval_off_min,
                repeat_days="mon,tue,wed,thu,fri,sat,sun",
                is_active=True,
                source=SCHEDULE_SOURCE_PLANT_AUTO,
            )
            for a in actuators
        ]


# Singleton
recipe_engine_service = RecipeEngineService()

