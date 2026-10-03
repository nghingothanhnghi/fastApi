# app/hydro_system/services/growth_recipe_service.py
from sqlalchemy.orm import Session
from typing import List, Optional
from app.hydro_system.models.growth_recipe import GrowthRecipe
from app.hydro_system.models.actuator import HydroActuator
from app.hydro_system.schemas.growth_recipe import GrowthRecipeCreate


class RecipeTargetError(ValueError):
    """actuator_id does not exist or does not match actuator_type."""


class GrowthRecipeService:

    def validate_target(
        self, db: Session, actuator_type: str, actuator_id: Optional[int]
    ) -> None:
        if actuator_id is None:
            return
        actuator = db.query(HydroActuator).filter(HydroActuator.id == actuator_id).first()
        if not actuator:
            raise RecipeTargetError(f"Actuator {actuator_id} not found")
        if actuator.type != actuator_type:
            raise RecipeTargetError(
                f"Actuator {actuator_id} is type '{actuator.type}', "
                f"recipe actuator_type is '{actuator_type}'"
            )

    def create_recipe(self, db: Session, recipe_in: GrowthRecipeCreate) -> GrowthRecipe:
        self.validate_target(db, recipe_in.actuator_type, recipe_in.actuator_id)
        recipe = GrowthRecipe(**recipe_in.dict())
        db.add(recipe)
        db.commit()
        db.refresh(recipe)
        return recipe

    def get_recipe(self, db: Session, recipe_id: int) -> Optional[GrowthRecipe]:
        return db.query(GrowthRecipe).filter(GrowthRecipe.id == recipe_id).first()

    def get_recipes_by_stage(self, db: Session, stage_id: int) -> List[GrowthRecipe]:
        return db.query(GrowthRecipe).filter(GrowthRecipe.stage_id == stage_id).all()

    def update_recipe(self, db: Session, recipe_id: int, updates: dict) -> Optional[GrowthRecipe]:
        recipe = self.get_recipe(db, recipe_id)
        if not recipe:
            return None
        # validate the merged result so partial updates are checked too
        self.validate_target(
            db,
            updates.get("actuator_type", recipe.actuator_type),
            updates.get("actuator_id", recipe.actuator_id),
        )
        for key, value in updates.items():
            setattr(recipe, key, value)
        db.commit()
        db.refresh(recipe)
        return recipe

    def delete_recipe(self, db: Session, recipe_id: int) -> bool:
        recipe = self.get_recipe(db, recipe_id)
        if not recipe:
            return False
        db.delete(recipe)
        db.commit()
        return True


growth_recipe_service = GrowthRecipeService()