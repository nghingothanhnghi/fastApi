# app/hydro_system/controllers/recipe_engine_controller.py
#
# STEP 1 FIX — this controller is now a thin shim.
#
# All logic has moved to:
#   app/hydro_system/services/recipe_engine_service.py
#
# This file is kept so existing route imports don't break.
# Routes that call recipe_engine_controller.apply_stage_recipes(...)
# continue to work without any changes.
#
# TODO: Once all callers are updated to import recipe_engine_service
#       directly, this file can be deleted.

from app.hydro_system.services.recipe_engine_service import recipe_engine_service
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class RecipeEngineController:
    """
    Backward-compatible shim.
    Delegates everything to RecipeEngineService.
    """

    def apply_stage_recipes(self, db, batch, recipes: list) -> None:
        recipe_engine_service.apply_stage_recipes(db=db, batch=batch, recipes=recipes)

    def apply_stage_recipe(self, db, batch, recipe) -> None:
        # Keep the single-recipe API available for any direct callers
        recipe_engine_service._apply_single_recipe(db=db, batch=batch, recipe=recipe)


# Singleton — same name as before so imports don't break
recipe_engine_controller = RecipeEngineController()
