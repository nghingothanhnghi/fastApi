# app/hydro_system/controllers/recipe_engine_controller.py
# Controller for applying growth recipes to the hydroponic system's schedule

from datetime import time

from app.hydro_system.services.actuator_service import hydro_actuator_service
from app.hydro_system.services.schedule_service import hydro_schedule_service
from app.hydro_system.models.schedule import HydroSchedule

class RecipeEngineController:


    def apply_stage_recipes(self, db, batch, recipes):
        """
        Apply multiple recipes at once for a stage.
        Ensures OLD schedules are deleted only once.
        """
        try:
            # 🔴 STEP 1: DELETE old auto schedules ONCE
            hydro_schedule_service.delete_by_device_and_source(
                db=db,
                device_id=batch.zone_id,
                source="plant_auto"
            )

            # 🟢 STEP 2: APPLY each recipe
            for recipe in recipes:
                self.apply_stage_recipe(db, batch, recipe, delete_existing=False, commit=False)

            # ✅ SINGLE COMMIT
            db.commit()
        except Exception:
            db.rollback()
            raise

    def apply_stage_recipe(self, db, batch, recipe, delete_existing=True, commit=True):
        """
        Apply a single recipe to a batch's zone (device).
        Handles OLD schedules deletion and NEW schedules creation for time-based recipes.
        """
        try:
            schedules_to_create = []

            actuators = hydro_actuator_service.get_active_actuators_by_type(
                db=db,
                actuator_type=recipe.actuator_type,
                device_id=batch.zone_id
            )

            if not actuators:
                print(f"[RecipeEngine] No actuators found for {recipe.actuator_type}")
                return

            # 🟢 ON
            if recipe.action == "on" and recipe.start_time and recipe.end_time:
                schedules_to_create = [
                    HydroSchedule(
                    actuator_id=a.id,
                    start_time=recipe.start_time,
                    end_time=recipe.end_time,
                    repeat_days="mon,tue,wed,thu,fri,sat,sun",
                    is_active=True,
                    source="plant_auto"
                )
                for a in actuators
            ]

            # 🟡 INTERVAL
            elif recipe.action == "interval" and recipe.interval_on_min and recipe.interval_off_min:
                start_time = recipe.start_time or time(0, 0)
                end_time = recipe.end_time or time(23, 59)

                schedules_to_create = [
                    HydroSchedule(
                        actuator_id=a.id,
                        start_time=start_time,
                        end_time=end_time,
                        interval_on_min=recipe.interval_on_min,
                        interval_off_min=recipe.interval_off_min,
                        repeat_days="mon,tue,wed,thu,fri,sat,sun",
                        is_active=True,
                        source="plant_auto"
                    )
                    for a in actuators
                ]

            else:
                print(f"[RecipeEngine] Invalid recipe: {recipe}")
                return

            if schedules_to_create:
                hydro_schedule_service.bulk_create(db, schedules_to_create, commit=False)

            if commit:
                # ✅ COMMIT
                db.commit()

        except Exception:
            if commit:
                db.rollback()
            raise


recipe_engine_controller = RecipeEngineController()