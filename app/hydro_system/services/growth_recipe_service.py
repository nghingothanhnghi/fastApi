from sqlalchemy.orm import Session
from typing import List, Optional
from app.hydro_system.models.growth_recipe import GrowthRecipe
from app.hydro_system.schemas.growth_recipe import GrowthRecipeCreate

class GrowthRecipeService:
    def create_recipe(self, db: Session, recipe_in: GrowthRecipeCreate) -> GrowthRecipe:
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
