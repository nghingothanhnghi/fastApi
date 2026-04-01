# app/hydro_system/controllers/recipe_engine_controller.py
# Controller for applying growth recipes to the hydroponic system's schedule

from app.hydro_system.services.actuator_service import hydro_actuator_service
from app.hydro_system.services.schedule_service import hydro_schedule_service
from app.hydro_system.models.schedule import HydroSchedule

class RecipeEngineController:

    def apply_recipe_to_schedule(self, db, batch, recipe):

        if not recipe.start_time or not recipe.end_time:
            return  # guard clause

        actuators = hydro_actuator_service.get_active_actuators_by_type(
            db=db,
            actuator_type=recipe.actuator_type,
            device_id=batch.zone_id
        )

        schedules_to_create = []

        for actuator in actuators:

            if hydro_schedule_service.exists_schedule(
                db=db,
                actuator_id=actuator.id,
                start_time=recipe.start_time,
                end_time=recipe.end_time,
                repeat_days="mon,tue,wed,thu,fri,sat,sun"
            ):
                continue

            schedules_to_create.append(
                HydroSchedule(
                    actuator_id=actuator.id,
                    start_time=recipe.start_time,
                    end_time=recipe.end_time,
                    repeat_days="mon,tue,wed,thu,fri,sat,sun",
                    is_active=True
                )
            )

        if schedules_to_create:
            hydro_schedule_service.bulk_create(db, schedules_to_create)