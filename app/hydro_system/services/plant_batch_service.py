from sqlalchemy.orm import Session
from typing import List, Optional
from app.hydro_system.models.plant_batch import PlantBatch
from app.hydro_system.schemas.batch import BatchCreate

class PlantBatchService:
    def create_batch(self, db: Session, batch_in: BatchCreate) -> PlantBatch:
        batch = PlantBatch(**batch_in.dict())
        db.add(batch)
        db.commit()
        db.refresh(batch)
        return batch

    def get_batch(self, db: Session, batch_id: int) -> Optional[PlantBatch]:
        return db.query(PlantBatch).filter(PlantBatch.id == batch_id).first()

    def get_all_batches(self, db: Session) -> List[PlantBatch]:
        return db.query(PlantBatch).all()

    def update_batch(self, db: Session, batch_id: int, updates: dict) -> Optional[PlantBatch]:
        batch = self.get_batch(db, batch_id)
        if not batch:
            return None
        for key, value in updates.items():
            setattr(batch, key, value)
        db.commit()
        db.refresh(batch)
        return batch

    def delete_batch(self, db: Session, batch_id: int) -> bool:
        batch = self.get_batch(db, batch_id)
        if not batch:
            return False
        db.delete(batch)
        db.commit()
        return True

plant_batch_service = PlantBatchService()
