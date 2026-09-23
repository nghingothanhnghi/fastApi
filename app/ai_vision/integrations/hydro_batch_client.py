# app/ai_vision/integrations/hydro_batch_client.py
from typing import Optional
from sqlalchemy.orm import Session
from app.hydro_system.models.plant_batch import PlantBatch
from app.hydro_system.models.plant import Plant
from app.hydro_system.models.growth_stage import GrowthStage

class HydroBatchClient:
    """Read-only reach into hydro_system for linking purposes.
    Same direction of dependency the rest of ai_vision already uses
    (hydroponic_client.py) — hydro_system never imports ai_vision."""

    def get_batch_with_plant(self, db: Session, batch_id: int) -> Optional[dict]:
        batch = db.query(PlantBatch).filter(PlantBatch.id == batch_id).first()
        if not batch:
            return None
        plant = db.query(Plant).filter(Plant.id == batch.plant_id).first()
        return {
            "batch_id": batch.id,
            "plant_id": batch.plant_id,
            "species": plant.name if plant else "Unknown",
            "zone_id": batch.zone_id,        # == HydroDevice.id
            "status": batch.status,
        }
    def get_batch_growth_timeline(self, db: Session, batch_id: int) -> Optional[dict]:
        """
        V5: read-only batch timing + stage window, used to project a
        stage-transition date against vision-measured growth rate. Never
        writes back to hydro_system.
        """
        batch = db.query(PlantBatch).filter(PlantBatch.id == batch_id).first()
        if not batch:
            return None

        stages = (
            db.query(GrowthStage)
            .filter(GrowthStage.plant_id == batch.plant_id)
            .order_by(GrowthStage.day_start.asc())
            .all()
        )

        current_stage = None
        next_stage = None
        for i, s in enumerate(stages):
            if s.id == batch.current_stage_id:
                current_stage = s
                next_stage = stages[i + 1] if i + 1 < len(stages) else None
                break

        return {
            "batch_id": batch.id,
            "start_date": batch.start_date,
            "status": batch.status,
            "current_stage_id": current_stage.id if current_stage else None,
            "current_stage_name": current_stage.name if current_stage else None,
            "current_stage_day_end": current_stage.day_end if current_stage else None,
            "next_stage_day_start": next_stage.day_start if next_stage else None,
        }    


hydro_batch_client = HydroBatchClient()