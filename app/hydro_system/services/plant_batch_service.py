# app/hydro_system/services/plant_batch_service.py
# Service layer for managing plant batches in the hydroponic system
from sqlalchemy.orm import Session, joinedload
from datetime import date
from typing import List, Optional
from app.hydro_system.models.plant_batch import PlantBatch
from app.hydro_system.models.growth_stage import GrowthStage
from app.hydro_system.schemas import batch
from app.hydro_system.schemas.batch import BatchCreate, BatchDetail
from app.hydro_system.controllers.recipe_engine_controller import recipe_engine_controller
from app.hydro_system.services import growth_recipe_service


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
        
        # ✅ preload all stages grouped by plant_id
        stages_by_plant = {}
        all_stages = db.query(GrowthStage)\
            .order_by(GrowthStage.day_start.asc())\
            .all()

        for s in all_stages:
            stages_by_plant.setdefault(s.plant_id, []).append(s)

        # ✅ update progress WITHOUT committing each time
        for b in batches:
            stages = stages_by_plant.get(b.plant_id, [])
            self.update_growth_progress(db, b, stages)

        # ✅ SINGLE COMMIT
        db.commit()

        # ✅ refresh relationship for all batches
        for b in batches:
            db.refresh(b, attribute_names=["current_stage"])

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
        
        # ✅ load stages once
        stages = db.query(GrowthStage)\
            .filter(GrowthStage.plant_id == batch.plant_id)\
            .order_by(GrowthStage.day_start.asc())\
            .all()

        self.update_growth_progress(db, batch, stages)

        db.commit()

        db.refresh(batch, attribute_names=["current_stage"])

        return self._map_to_detail(batch)
    
    def update_growth_progress(self, db: Session, batch: PlantBatch, stages: list[GrowthStage]):

        if not batch.start_date or not stages:
            return batch

        days = (date.today() - batch.start_date).days

        current_stage = None

        for i, stage in enumerate(stages):
            next_stage = stages[i + 1] if i + 1 < len(stages) else None

            if stage.day_start <= days and (not next_stage or days < next_stage.day_start):
                current_stage = stage
                break

        
        old_stage_id = batch.current_stage_id
        old_status = batch.status    

        new_stage_id = None
        new_status = batch.status

        if current_stage:
            new_stage_id = current_stage.id
            new_status = "harvesting" if current_stage == stages[-1] else "growing"
        else:
            if days > stages[-1].day_end:
                new_stage_id = stages[-1].id
                new_status = "completed"
            elif days < stages[0].day_start:
                new_stage_id = None
                new_status = "seeded"

        stage_changed = old_stage_id != new_stage_id

        # ✅ update batch state
        if stage_changed or old_status != new_status:
            batch.current_stage_id = new_stage_id
            batch.status = new_status        

        # 🔥🔥🔥 TRIGGER RECIPE ENGINE HERE
        if stage_changed and new_stage_id:
            recipes = growth_recipe_service.get_recipes_by_stage(db, new_stage_id)

            if recipes:
                recipe_engine_controller.apply_stage_recipes(
                    db=db,
                    batch=batch,
                    recipes=recipes
                )

        return batch

plant_batch_service = PlantBatchService()
