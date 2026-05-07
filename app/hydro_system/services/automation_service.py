from sqlalchemy.orm import Session, joinedload
from datetime import date

from app.hydro_system.models.plant_batch import PlantBatch
from app.hydro_system.models.growth_stage import GrowthStage

from app.hydro_system.services.plant_batch_service import plant_batch_service
from app.hydro_system.services.growth_recipe_service import growth_recipe_service

from app.hydro_system.controllers.recipe_engine_controller import recipe_engine_controller
from app.hydro_system.controllers.actuator_controller import control_actuator_by_id
from app.hydro_system.state_manager import get_state, set_state

from app.hydro_system.rules_engine import check_rules


class AutomationService:

    # =========================
    # 🌱 STAGE + RECIPE ENGINE
    # =========================
    def run_growth_cycle(self, db: Session):

        try:

            batches = db.query(PlantBatch).all()

            all_stages = (
                db.query(GrowthStage)
                .options(joinedload(GrowthStage.recipes))
                .order_by(GrowthStage.day_start.asc())
                .all()
            )

            stages_by_plant = {}

            for stage in all_stages:
                stages_by_plant.setdefault(
                    stage.plant_id,
                    []
                ).append(stage)

            for batch in batches:

                stages = stages_by_plant.get(
                    batch.plant_id,
                    []
                )

                old_stage_id = batch.current_stage_id

                plant_batch_service.update_growth_progress(
                    db,
                    batch,
                    stages
                )

                # stage changed
                if old_stage_id != batch.current_stage_id:

                    current_stage = next(
                        (
                            s for s in stages
                            if s.id == batch.current_stage_id
                        ),
                        None
                    )

                    if current_stage and current_stage.recipes:

                        recipe_engine_controller.apply_stage_recipes(
                            db=db,
                            batch=batch,
                            recipes=current_stage.recipes
                        )

                        print(
                            f"[Automation] "
                            f"batch={batch.id} "
                            f"stage={current_stage.name}"
                        )

            db.commit()

        except Exception:
            db.rollback()
            raise

    # =========================
    # ⚡ REAL-TIME CONTROL
    # =========================
    def run_control_loop(
        self,
        db: Session,
        sensor_data: dict,
        actuators: list,
        batch: PlantBatch = None
    ):
        """
        Run frequently (every few seconds).
        Handles:
        - rule engine decisions
        - actuator ON/OFF
        """
        # get current stage recipes
        recipes = []

        if batch and batch.current_stage_id:
            recipes = growth_recipe_service.get_recipes_by_stage(
                db,
                batch.current_stage_id
            )

        result = check_rules(
            sensor_data=sensor_data,
            actuators=actuators,
            recipes=recipes
        )

        # 🔥 Execute actions
        actions_taken = {}
        for action in result.get("actions", []):
            actuator_id = action["actuator_id"]
            should_on = action["on"]
            actuator_type = action["type"]
            
            # Find the actuator object for device/port info
            actuator = next((a for a in actuators if a.id == actuator_id), None)
            if not actuator:
                continue

            actuator_key = f"{actuator_type}_{actuator.device_id}_{actuator.port}"
            prev_state = get_state(actuator_key)

            if should_on != prev_state:
                control_actuator_by_id(db, actuator_id, should_on, source="automation")
                set_state(actuator_key, should_on)
                actions_taken[actuator_key] = should_on

        return {
            "actions_taken": actions_taken,
            "alerts": result.get("alerts", []),
            "result": result
        }


automation_service = AutomationService()