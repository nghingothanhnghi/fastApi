from sqlalchemy.orm import Session, joinedload
from datetime import date
from typing import List, Optional
from app.hydro_system.models.plant_batch import PlantBatch
from app.hydro_system.schemas import batch
from app.hydro_system.schemas.batch import BatchCreate, BatchDetail

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
    
    def _map_to_detail(self, batch: PlantBatch) -> BatchDetail:
        return BatchDetail(
            id=batch.id,
            plant_id=batch.plant_id,
            current_stage_id=batch.current_stage_id,
            zone_id=batch.zone_id,
            start_date=batch.start_date,
            status=batch.status,

            # 👇 computed
            plant_name=batch.plant.name if batch.plant else None,
            current_stage_name=batch.current_stage.name if batch.current_stage else None,
            days_growing=(date.today() - batch.start_date).days if batch.start_date else None,

            device_name=batch.device.device_id if batch.device else None,
            device_location=batch.device.location if batch.device else None,
    )

    def get_all_batches_detail(self, db: Session) -> List[BatchDetail]:
        batches = db.query(PlantBatch)\
            .options(
                joinedload(PlantBatch.plant),
                joinedload(PlantBatch.current_stage),
                joinedload(PlantBatch.device)
            )\
            .all()
        return [self._map_to_detail(b) for b in batches]
    
    def get_batch_detail(self, db: Session, batch_id: int) -> Optional[BatchDetail]:
        batch = db.query(PlantBatch)\
            .options(
                joinedload(PlantBatch.plant),
                joinedload(PlantBatch.current_stage)
            )\
            .filter(PlantBatch.id == batch_id)\
            .first()

        if not batch:
            return None

        return self._map_to_detail(batch)

plant_batch_service = PlantBatchService()
