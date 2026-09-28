# app/hydro_system/services/plant_service.py
from sqlalchemy.orm import Session
from typing import List, Optional
from app.hydro_system.models.plant import Plant
from app.hydro_system.schemas.plant import PlantCreate
from app.hydro_system.schemas.growth_plan import GrowthPlanCreate
from app.hydro_system.services.growth_plan_service import growth_plan_service

class PlantService:
    def create_plant(self, db: Session, plant_in: PlantCreate) -> Plant:
        plant = Plant(**plant_in.dict())
        db.add(plant)
        db.commit()
        db.refresh(plant)

        # Every plant must have at least one (default) plan, otherwise a
        # batch created for it has plan_id=None and can never progress.
        growth_plan_service.create_plan(
            db,
            GrowthPlanCreate(
                plant_id=plant.id,
                name="Default Plan",
                is_default=True,
            ),
        )
        return plant

    def get_plant(self, db: Session, plant_id: int) -> Optional[Plant]:
        return db.query(Plant).filter(Plant.id == plant_id).first()

    def get_all_plants(self, db: Session) -> List[Plant]:
        return db.query(Plant).all()

    def update_plant(self, db: Session, plant_id: int, updates: dict) -> Optional[Plant]:
        plant = self.get_plant(db, plant_id)
        if not plant:
            return None
        for key, value in updates.items():
            setattr(plant, key, value)
        db.commit()
        db.refresh(plant)
        return plant

    def delete_plant(self, db: Session, plant_id: int) -> bool:
        plant = self.get_plant(db, plant_id)
        if not plant:
            return False
        db.delete(plant)
        db.commit()
        return True

plant_service = PlantService()
