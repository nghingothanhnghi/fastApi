from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from app.hydro_system.models.growth_recipe import GrowthRecipe
from app.hydro_system.models.growth_stage import GrowthStage
from app.hydro_system.schemas.growth_stage import GrowthStageCreate, GrowthStageWithRecipesUpdate

class GrowthStageService:
    def create_stage(self, db: Session, stage_in: GrowthStageCreate) -> GrowthStage:
        stage = GrowthStage(**stage_in.dict())
        db.add(stage)
        db.commit()
        db.refresh(stage)
        return stage

    def get_stage(self, db: Session, stage_id: int) -> Optional[GrowthStage]:
        return db.query(GrowthStage).filter(GrowthStage.id == stage_id).first()

    def get_stages_by_plant(self, db: Session, plant_id: int):
        return (
            db.query(GrowthStage)
            .options(joinedload(GrowthStage.recipes))
            .filter(GrowthStage.plant_id == plant_id)
            .all()
        )
    
    def update_stage(self, db: Session, stage_id: int, updates: dict) -> Optional[GrowthStage]:
        stage = self.get_stage(db, stage_id)
        if not stage:
            return None
        for key, value in updates.items():
            setattr(stage, key, value)
        db.commit()
        db.refresh(stage)
        return stage

    def update_stage_with_recipes(
        self,
        db: Session,
        stage_id: int,
        data: GrowthStageWithRecipesUpdate
    ) -> Optional[GrowthStage]:

        stage = self.get_stage(db, stage_id)
        if not stage:
            return None

        # ✅ update stage
        stage.name = data.name
        stage.day_start = data.day_start
        stage.day_end = data.day_end

        # ✅ delete old recipes
        db.query(GrowthRecipe).filter(
            GrowthRecipe.stage_id == stage_id
        ).delete()

        # ✅ insert new recipes
        for r in data.recipes:
            db.add(GrowthRecipe(**r.dict(), stage_id=stage_id))

        db.commit()
        db.refresh(stage)

        return stage

    def delete_stage(self, db: Session, stage_id: int) -> bool:
        stage = self.get_stage(db, stage_id)
        if not stage:
            return False
        db.delete(stage)
        db.commit()
        return True

growth_stage_service = GrowthStageService()
