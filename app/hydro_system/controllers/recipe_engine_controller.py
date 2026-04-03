# app/hydro_system/controllers/recipe_engine_controller.py
# Controller for applying growth recipes to the hydroponic system's schedule

from app.hydro_system.services.actuator_service import hydro_actuator_service
from app.hydro_system.services.schedule_service import hydro_schedule_service
from app.hydro_system.models.schedule import HydroSchedule

class RecipeEngineController:


    def apply_stage_recipe(self, db, batch, recipe):
        """
        Apply a recipe to a batch's zone (device).
        Handles OLD schedules deletion and NEW schedules creation for time-based recipes.
        Interval-based recipes are handled at runtime by the rules engine.
        """
        try:
            # 🔴 STEP 1: DELETE old auto schedules (Always do this when changing stage/recipe)
            hydro_schedule_service.delete_by_device_and_source(
                db=db,
                device_id=batch.zone_id,
                source="plant_auto"
            )

            # 🟢 STEP 2: IF recipe has time parameters → CREATE NEW schedules
            if recipe.start_time and recipe.end_time:
                actuators = hydro_actuator_service.get_active_actuators_by_type(
                    db=db,
                    actuator_type=recipe.actuator_type,
                    device_id=batch.zone_id
                )

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

                if schedules_to_create:
                    hydro_schedule_service.bulk_create(
                        db,
                        schedules_to_create,
                        commit=False
                    )

            # 🟡 STEP 3: IF recipe has interval parameters → (Runtime logic in rules_engine)
            # No HydroSchedule needed for interval mode, it's checked by the automation loop.

            # ✅ SINGLE COMMIT (atomic)
            db.commit()

        except Exception:
            db.rollback()
            raise


recipe_engine_controller = RecipeEngineController()