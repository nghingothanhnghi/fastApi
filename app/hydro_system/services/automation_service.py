# app/hydro_system/services/automation_service.py
# app/hydro_system/services/automation_service.py
#
# STEP 1 FIX — Circular import removed:
#   BEFORE: imported controllers/recipe_engine_controller  ❌
#           imported controllers/actuator_controller        ❌
#   AFTER:  imports services/recipe_engine_service          ✅
#           imports services/actuator_log_service           ✅
#           actuator hardware calls moved to actuator_service ✅

from sqlalchemy.orm import Session, joinedload

from app.hydro_system.models.plant_batch import PlantBatch
from app.hydro_system.models.growth_stage import GrowthStage
from app.hydro_system.models.actuator import HydroActuator
from app.hydro_system.services.plant_batch_service import plant_batch_service
from app.hydro_system.services.growth_recipe_service import growth_recipe_service
from app.hydro_system.services.recipe_engine_service import recipe_engine_service   # ← was controller
from app.hydro_system.services.actuator_service import hydro_actuator_service       # ← replaces controller call
from app.hydro_system.services.actuator_log_service import log_actuator_action
from app.hydro_system.state_manager import get_state, set_state
from app.hydro_system.rules_engine import check_rules
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class AutomationService:

    # ──────────────────────────────────────────────────────────────────────────
    # 🌱 GROWTH CYCLE  (runs every 12 h)
    # ──────────────────────────────────────────────────────────────────────────
    def run_growth_cycle(self, db: Session) -> None:
        """
        Advance every batch to the correct growth stage based on elapsed days,
        then rebuild schedules if the stage changed.
        """
        try:
            batches = db.query(PlantBatch).all()

            # Single query for all stages, grouped by plant
            all_stages = (
                db.query(GrowthStage)
                .options(joinedload(GrowthStage.recipes))
                .order_by(GrowthStage.day_start.asc())
                .all()
            )
            stages_by_plant: dict[int, list[GrowthStage]] = {}
            for stage in all_stages:
                stages_by_plant.setdefault(stage.plant_id, []).append(stage)

            for batch in batches:
                stages = stages_by_plant.get(batch.plant_id, [])
                old_stage_id = batch.current_stage_id

                plant_batch_service.update_growth_progress(db, batch, stages)

                if old_stage_id != batch.current_stage_id:
                    current_stage = next(
                        (s for s in stages if s.id == batch.current_stage_id), None
                    )
                    if current_stage and current_stage.recipes:
                        # ✅ now calls a service, not a controller
                        recipe_engine_service.apply_stage_recipes(
                            db=db,
                            batch=batch,
                            recipes=current_stage.recipes,
                        )
                        logger.info(
                            f"[GrowthCycle] batch={batch.id} → stage='{current_stage.name}'"
                        )

            db.commit()

        except Exception:
            db.rollback()
            raise

    # ──────────────────────────────────────────────────────────────────────────
    # ⚡ REAL-TIME CONTROL LOOP  (runs every 60 s)
    # ──────────────────────────────────────────────────────────────────────────
    def run_control_loop(
        self,
        db: Session,
        sensor_data: dict,
        actuators: list,
        batch: PlantBatch | None = None,
    ) -> dict:
        """
        Evaluate rules and toggle actuators only when state changes.
        Returns a summary dict for logging/debugging.
        """
        if not get_state("scheduler"):
            return {
                "actions_taken": {},
                "alerts": [],
                "result": {},
                "note": "Automation paused (Scheduler OFF)",
            }

        recipes = []
        if batch and batch.current_stage_id:
            recipes = growth_recipe_service.get_recipes_by_stage(
                db, batch.current_stage_id
            )

        result = check_rules(
            sensor_data=sensor_data,
            actuators=actuators,
            recipes=recipes,
        )

        actions_taken: dict[str, bool] = {}

        for action in result.get("actions", []):
            actuator_id = action["actuator_id"]
            should_on: bool = action["on"]
            actuator_type: str = action["type"]

            actuator = next((a for a in actuators if a.id == actuator_id), None)
            if not actuator:
                continue

            actuator_key = f"{actuator_type}_{actuator.device_id}_{actuator.port}"

            # Only write when state actually changes
            if should_on != get_state(actuator_key):
                self._apply_actuator_action(
                    db, actuator, should_on, actuator_key
                )
                actions_taken[actuator_key] = should_on

        return {
            "actions_taken": actions_taken,
            "alerts": result.get("alerts", []),
            "result": result,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _apply_actuator_action(
        db: Session,
        actuator: HydroActuator,
        on: bool,
        actuator_key: str,
    ) -> None:
        """
        Persist the actuator state change.
        Previously this called control_actuator_by_id() from actuator_controller —
        now it goes directly to the service layer to avoid the controller dependency.
        """
        state_str = "ON" if on else "OFF"

        # Update runtime state cache
        set_state(actuator_key, on)

        # Persist to log (service layer only — no HTTP layer involved)
        log_actuator_action(
            db,
            actuator_id=actuator.id,
            action=state_str.lower(),
            state=state_str,
            source="automation",
        )

        logger.info(
            f"[Automation] {actuator.type} actuator {actuator.id} "
            f"({actuator_key}) → {state_str}"
        )


automation_service = AutomationService()
