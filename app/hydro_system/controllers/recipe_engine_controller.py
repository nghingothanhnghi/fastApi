# app/hydro_system/controllers/recipe_engine_controller.py
# Controller for applying growth recipes to the hydroponic system's schedule

from app.hydro_system.services.actuator_service import hydro_actuator_service
from app.hydro_system.services.schedule_service import hydro_schedule_service
from app.hydro_system.models.schedule import HydroSchedule

class RecipeEngineController:


    def apply_stage_recipe(self, db, batch, recipe):

        if not recipe.start_time or not recipe.end_time:
            return

        try:
            # 🔴 STEP 1: DELETE old auto schedules
            hydro_schedule_service.delete_by_device_and_source(
                db=db,
                device_id=batch.zone_id,
                source="plant_auto"
            )

            # 🟢 STEP 2: GET actuators
            actuators = hydro_actuator_service.get_active_actuators_by_type(
                db=db,
                actuator_type=recipe.actuator_type,
                device_id=batch.zone_id
            )

            # 🔵 STEP 3: BUILD schedules
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

            # 🟣 STEP 4: INSERT (no commit yet)
            if schedules_to_create:
                hydro_schedule_service.bulk_create(
                    db,
                    schedules_to_create,
                    commit=False
                )

            # ✅ SINGLE COMMIT (atomic)
            db.commit()

        except Exception:
            db.rollback()
            raise


recipe_engine_controller = RecipeEngineController()