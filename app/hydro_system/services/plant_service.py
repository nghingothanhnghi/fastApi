from sqlalchemy.orm import Session
from typing import List, Optional
from app.hydro_system.models.plant import Plant
from app.hydro_system.schemas.plant import PlantCreate

class PlantService:
    def create_plant(self, db: Session, plant_in: PlantCreate) -> Plant:
        plant = Plant(**plant_in.dict())
        db.add(plant)
        db.commit()
        db.refresh(plant)
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
