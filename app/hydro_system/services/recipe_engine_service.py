# app/hydro_system/services/recipe_engine_service.py
#
# RULE: services → models/schemas only.
#       controllers → services only.
#       No service may import a controller.

from datetime import time
from sqlalchemy.orm import Session

from app.hydro_system.services.actuator_service import hydro_actuator_service
from app.hydro_system.services.schedule_service import hydro_schedule_service
from app.hydro_system.models.schedule import HydroSchedule
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Single source of truth for the schedule source tag used by plant recipes.
SCHEDULE_SOURCE_PLANT_AUTO = "plant_auto"


class RecipeEngineService:
    """
    Translates GrowthRecipe rows into HydroSchedule rows.

    Responsibilities:
    - Delete old plant-auto schedules for a device zone.
    - Create new schedules derived from a growth stage's recipe list.

    No HTTP, no FastAPI dependencies — pure DB logic.

    TRANSACTIONS: this service never commits or rolls back. The caller owns
    the transaction (delete + inserts land together, or not at all).
    """

    def apply_stage_recipes(self, db: Session, batch, recipes: list) -> None:
        """
        Apply all recipes for a growth stage to the batch's zone (device).

        1. Guard: a batch with no zone has nowhere to schedule.
        2. Delete existing plant_auto schedules for the zone in ONE query.
        3. Create new schedules from the recipe list.
        4. Caller commits.
        """
        if batch.zone_id is None:
            # Without this, device_id=None would skip the device filter in
            # get_active_actuators_by_type and schedule EVERY device's actuators.
            logger.warning(
                f"[RecipeEngine] Batch {batch.id} has no zone_id — "
                f"no schedules applied."
            )
            return

        hydro_schedule_service.delete_by_device_and_source(
            db=db,
            device_id=batch.zone_id,
            source=SCHEDULE_SOURCE_PLANT_AUTO,
        )

        for recipe in recipes:
            self._apply_single_recipe(db, batch, recipe)

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _apply_single_recipe(self, db: Session, batch, recipe) -> None:
        """Build HydroSchedule rows for one recipe and bulk-insert them."""
        # Also guarded here: the controller shim exposes this directly.
        if batch.zone_id is None:
            logger.warning(
                f"[RecipeEngine] Batch {batch.id} has no zone_id — "
                f"recipe skipped."
            )
            return

        actuators = hydro_actuator_service.get_active_actuators_by_type(
            db=db,
            actuator_type=recipe.actuator_type,
            device_id=batch.zone_id,
        )

        if not actuators:
            logger.warning(
                f"[RecipeEngine] No active '{recipe.actuator_type}' actuators "
                f"on device {batch.zone_id} — skipping recipe."
            )
            return

        schedules = self._build_schedules(actuators, recipe)

        if schedules:
            hydro_schedule_service.bulk_create(db, schedules, commit=False)
            logger.info(
                f"[RecipeEngine] Created {len(schedules)} schedule(s) "
                f"for '{recipe.actuator_type}' (action={recipe.action})."
            )

    def _build_schedules(self, actuators: list, recipe) -> list[HydroSchedule]:
        """Return the correct schedule list for 'on' or 'interval' recipes."""
        if recipe.action == "on":
            return self._build_on_schedules(actuators, recipe)
        if recipe.action == "interval":
            return self._build_interval_schedules(actuators, recipe)

        logger.warning(f"[RecipeEngine] Unknown recipe action '{recipe.action}' — skipped.")
        return []

    @staticmethod
    def _build_on_schedules(actuators: list, recipe) -> list[HydroSchedule]:
        if not recipe.start_time or not recipe.end_time:
            logger.warning("[RecipeEngine] 'on' recipe missing start_time/end_time — skipped.")
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
    def _build_interval_schedules(actuators: list, recipe) -> list[HydroSchedule]:
        if not recipe.interval_on_min or not recipe.interval_off_min:
            logger.warning("[RecipeEngine] 'interval' recipe missing interval values — skipped.")
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

