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
        """
        Run periodically (cronjob).
        Handles:
        - stage transitions
        - recipe engine trigger
        """

        batches = db.query(PlantBatch).all()

        # preload stages
        stages_by_plant = {}
        all_stages = db.query(GrowthStage)\
            .order_by(GrowthStage.day_start.asc())\
            .all()

        for s in all_stages:
            stages_by_plant.setdefault(s.plant_id, []).append(s)

        for batch in batches:
            stages = stages_by_plant.get(batch.plant_id, [])

            # This service handles both stage update AND RecipeEngine trigger
            plant_batch_service.update_growth_progress(db, batch, stages)

        db.commit()

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