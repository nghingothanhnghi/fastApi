# app/hydro_system/services/automation_service.py

from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.hydro_system.models.plant_batch import PlantBatch
from app.hydro_system.models.growth_stage import GrowthStage
from app.hydro_system.models.actuator import HydroActuator

from app.hydro_system.services.plant_batch_service import plant_batch_service
from app.hydro_system.services.actuator_service import hydro_actuator_service
from app.hydro_system.services.actuator_log_service import log_actuator_action
from app.hydro_system.services.flow_reading_service import flow_reading_service
from app.hydro_system.services.rain_debounce_service import rain_debounce_service

from app.hydro_system.config import SUPPORTED_ACTUATOR_TYPES, ACTIVE_BATCH_STATUSES
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

            # A plant can have multiple GrowthPlans, each with its own
            # independent timeline: group stages by plan.
            stages_by_plan: dict[int, list[GrowthStage]] = {}
            for stage in all_stages:
                if stage.plan_id:
                    stages_by_plan.setdefault(stage.plan_id, []).append(stage)

            for batch in batches:
                old_stage_id = batch.current_stage_id
                old_status = batch.status

                # update_growth_progress() owns everything: stage resolution,
                # applying recipes, clearing stale plant_auto schedules (empty
                # stage / batch leaving the active lifecycle), and skipping
                # manually finished (harvested/failed) or plan-less batches.
                plant_batch_service.update_growth_progress(
                    db,
                    batch,
                    stages_by_plan.get(batch.plan_id, []),
                )

                if old_stage_id != batch.current_stage_id:
                    logger.info(
                        f"[GrowthCycle] batch={batch.id} "
                        f"stage {old_stage_id} → {batch.current_stage_id}"
                    )
                if old_status != batch.status:
                    logger.info(
                        f"[GrowthCycle] batch={batch.id} "
                        f"status {old_status} → {batch.status}"
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

        NOTE: unchanged by multi-plan support. This loop already resolves
        recipes purely from `batch.current_stage.recipes` (a concrete
        GrowthStage the batch is currently on), so it has no dependency on
        plant_id vs plan_id — whichever plan produced that stage, the
        recipes attached to it are applied exactly the same way.        
        """

        alerts = []
        actions_taken = {}

        try:

            # ──────────────────────────────────────────────────────────────
            # Debounce rain_detected before it can influence control
            # ──────────────────────────────────────────────────────────────
            # A single noisy/stuck reading previously forced every
            # water-related actuator OFF immediately (see the rain branch
            # in rules_engine.check_rules), bypassing manual and scheduled
            # control. Require several consecutive agreeing readings
            # before the effective rain state can flip.
            raw_rain_detected = bool(sensor_data.get("rain_detected", False))
            effective_rain_detected = rain_debounce_service.get_effective_rain_state(
                db, device_id, raw_rain_detected
            )
            if effective_rain_detected != raw_rain_detected:
                sensor_data = {**sensor_data, "rain_detected": effective_rain_detected}

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
                    PlantBatch.status.in_(ACTIVE_BATCH_STATUSES),   # was == "growing"                
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
        
            # Faster lookup
            actuator_map = {
                actuator.id: actuator
                for actuator in actuators
            }

            # ✅ NEW — fetch latest flow reading per actuator in one query
            flow_readings = flow_reading_service.get_latest_map_for_actuators(
                db, list(actuator_map.keys())
            )            

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
                    prev_state = actuator.current_state

                    if desired_state != prev_state:

                        self._apply_actuator_action(
                            db=db,
                            actuator=actuator,
                            on=desired_state,
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
            # STEP 2 — RULE EVALUATION
            # ──────────────────────────────────────────────────────────────

            result = check_rules(
                sensor_data=sensor_data,
                actuators=auto_actuators,
                recipes=recipes,
                flow_readings=flow_readings,
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
            # STEP 3 — APPLY ACTIONS
            # ──────────────────────────────────────────────────────────────

            for action in result.get("actions", []):

                actuator_id = action["actuator_id"]
                should_on = action["on"]

                actuator = actuator_map.get(actuator_id)

                if not actuator:
                    continue

                actuator_key = (
                    f"{actuator.type}_"
                    f"{actuator.device_id}_"
                    f"{actuator.port}"
                )

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

            # ✅ SINGLE COMMIT
            db.commit()        

            return {
                "actions_taken": actions_taken,
                "alerts": alerts,
                "sensor_data": sensor_data,
            }
        
        except Exception:

            db.rollback()

            logger.exception(
                "[Automation] Control loop failed"
            )

            raise

    # ──────────────────────────────────────────────────────────────────────
    # INTERNAL HELPERS
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _apply_actuator_action(
        db: Session,
        actuator: HydroActuator,
        on: bool,
        source: str = "automation",
    ) -> None:

        state_str = "ON" if on else "OFF"

        # TODO:
        # hardware_driver.execute(actuator, on)
        # ✅ Persist REAL runtime state
        actuator.current_state = on
        actuator.last_state_changed_at = datetime.now(timezone.utc)

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
            f"({actuator.name}) -> {state_str}"
        )


automation_service = AutomationService()