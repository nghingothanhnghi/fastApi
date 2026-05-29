# app/hydro_system/services/automation_service.py

from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.hydro_system.models.plant_batch import PlantBatch
from app.hydro_system.models.growth_stage import GrowthStage
from app.hydro_system.models.actuator import HydroActuator

from app.hydro_system.services.plant_batch_service import plant_batch_service
from app.hydro_system.services.growth_recipe_service import growth_recipe_service
from app.hydro_system.services.recipe_engine_service import recipe_engine_service
from app.hydro_system.services.actuator_service import hydro_actuator_service
from app.hydro_system.services.actuator_log_service import log_actuator_action

from app.hydro_system.config import SUPPORTED_ACTUATOR_TYPES
from app.hydro_system.state_manager import get_state, set_state
from app.hydro_system.rules_engine import check_rules

from app.core.logging_config import get_logger

logger = get_logger(__name__)


class AutomationService:

    # ──────────────────────────────────────────────────────────────────────
    # 🌱 GROWTH CYCLE
    # ──────────────────────────────────────────────────────────────────────

    def run_growth_cycle(self, db: Session) -> None:
        try:
            batches = db.query(PlantBatch).all()

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

                plant_batch_service.update_growth_progress(
                    db,
                    batch,
                    stages,
                )

                if old_stage_id != batch.current_stage_id:

                    current_stage = next(
                        (
                            s for s in stages
                            if s.id == batch.current_stage_id
                        ),
                        None
                    )

                    if current_stage and current_stage.recipes:

                        recipe_engine_service.apply_stage_recipes(
                            db=db,
                            batch=batch,
                            recipes=current_stage.recipes,
                        )

                        logger.info(
                            f"[GrowthCycle] batch={batch.id} "
                            f"→ stage='{current_stage.name}'"
                        )

            db.commit()

        except Exception:
            db.rollback()
            raise

    # ──────────────────────────────────────────────────────────────────────
    # ⚡ REAL-TIME AUTOMATION LOOP
    # ──────────────────────────────────────────────────────────────────────

    def run_control_loop(
        self,
        db: Session,
        sensor_data: dict,
        device_id: int | None = None,
    ) -> dict:
        """
        Main automation engine.

        Responsibilities:
        - Load actuators
        - Load recipes
        - Apply manual overrides
        - Evaluate automation rules
        - Execute state changes
        """

        alerts = []
        actions_taken = {}

        scheduler_active = get_state("scheduler")

        # ──────────────────────────────────────────────────────────────
        # Load active batch + recipes
        # ──────────────────────────────────────────────────────────────

        recipes = []

        batch = (
            db.query(PlantBatch)
            .options(
                joinedload(PlantBatch.current_stage)
                .joinedload(GrowthStage.recipes)
            )
            .filter(
                PlantBatch.zone_id == device_id,
                PlantBatch.status == "growing",
            )
            .first()
        )

        if batch and batch.current_stage:
            recipes = batch.current_stage.recipes

            logger.debug(
                f"[Automation] Found {len(recipes)} recipes "
                f"for Batch {batch.id}"
            )

        # ──────────────────────────────────────────────────────────────
        # Load actuators
        # ──────────────────────────────────────────────────────────────

        actuators: list[HydroActuator] = []

        for device_type in SUPPORTED_ACTUATOR_TYPES:

            type_actuators = (
                hydro_actuator_service.get_all_actuators_by_type(
                    db,
                    device_type,
                    device_id=device_id,
                )
            )

            actuators.extend(type_actuators)

        if not actuators:
            logger.warning(
                f"[Automation] No actuators found "
                f"for device '{device_id}'"
            )

            return {
                "actions_taken": {},
                "alerts": [],
                "sensor_data": sensor_data,
            }

        # ──────────────────────────────────────────────────────────────
        # STEP 1 — MANUAL OVERRIDE
        # ──────────────────────────────────────────────────────────────

        auto_actuators = []

        for actuator in actuators:

            actuator_key = (
                f"{actuator.type}_"
                f"{actuator.device_id}_"
                f"{actuator.port}"
            )

            # Manual override has highest priority
            if actuator.manual_state is not None:

                desired_state = actuator.manual_state
                # prev_state = get_state(actuator_key)
                prev_state = actuator.current_state

                if desired_state != prev_state:

                    self._apply_actuator_action(
                        db=db,
                        actuator=actuator,
                        on=desired_state,
                        # actuator_key=actuator_key,
                        source="manual",
                    )

                    logger.info(
                        f"[MANUAL OVERRIDE] "
                        f"{actuator_key} -> {desired_state}"
                    )

                    actions_taken[actuator_key] = {
                        "activated": desired_state,
                        "mode": "manual",
                    }

                continue

            auto_actuators.append(actuator)

        # ──────────────────────────────────────────────────────────────
        # STEP 2 — AUTOMATION DISABLED
        # ──────────────────────────────────────────────────────────────

        if not scheduler_active:

            logger.debug(
                "[Automation] Scheduler OFF "
                "- skipping automatic control"
            )

            return {
                "actions_taken": actions_taken,
                "alerts": alerts,
                "sensor_data": sensor_data,
                "note": "Scheduler OFF",
            }

        # ──────────────────────────────────────────────────────────────
        # STEP 3 — RULE EVALUATION
        # ──────────────────────────────────────────────────────────────

        result = check_rules(
            sensor_data=sensor_data,
            actuators=auto_actuators,
            recipes=recipes,
        )

        # Collect alerts
        for alert in result.get("alerts", []):

            level = alert.get("type", "info")
            message = alert.get("message", "")

            getattr(logger, level, logger.info)(
                f"{level.upper()} ALERT: {message}"
            )

            alerts.append(alert)

        # ──────────────────────────────────────────────────────────────
        # STEP 4 — APPLY ACTIONS
        # ──────────────────────────────────────────────────────────────

        for action in result.get("actions", []):

            actuator_id = action["actuator_id"]
            should_on = action["on"]

            actuator = next(
                (a for a in auto_actuators if a.id == actuator_id),
                None,
            )

            if not actuator:
                continue

            actuator_key = (
                f"{actuator.type}_"
                f"{actuator.device_id}_"
                f"{actuator.port}"
            )

            # prev_state = get_state(actuator_key)
            prev_state = actuator.current_state

            # Only apply changes
            if should_on != prev_state:

                self._apply_actuator_action(
                    db=db,
                    actuator=actuator,
                    on=should_on,
                    # actuator_key=actuator_key,
                    source="automation",
                )

                logger.info(
                    f"[Automation] "
                    f"{actuator_key} -> {should_on}"
                )

                actions_taken[actuator_key] = {
                    "activated": should_on,
                    "mode": "automation",
                }

            else:

                logger.debug(
                    f"[Automation] No change for "
                    f"{actuator_key}, remains {prev_state}"
                )

        return {
            "actions_taken": actions_taken,
            "alerts": alerts,
            "sensor_data": sensor_data,
        }

    # ──────────────────────────────────────────────────────────────────────
    # INTERNAL HELPERS
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _apply_actuator_action(
        db: Session,
        actuator: HydroActuator,
        on: bool,
        # actuator_key: str,
        source: str = "automation",
    ) -> None:

        state_str = "ON" if on else "OFF"

        # Runtime state cache
        # set_state(actuator_key, on)

        # ✅ Persist REAL runtime state
        actuator.current_state = on
        actuator.last_state_changed_at = datetime.now(timezone.utc)

        
        db.commit()
        db.refresh(actuator)

        # TODO:
        # hardware_driver.execute(actuator, on)

        # Persist action log
        log_actuator_action(
            db=db,
            actuator_id=actuator.id,
            action=state_str.lower(),
            state=state_str,
            source=source,
        )

        logger.info(
            f"[Actuator] "
            f"{actuator.type} actuator {actuator.id} "
            # f"({actuator_key}) -> {state_str}"
        )


automation_service = AutomationService()