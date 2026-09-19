# app/ai_vision/integrations/hydro_batch_client.py
from typing import Optional
from sqlalchemy.orm import Session
from app.hydro_system.models.plant_batch import PlantBatch
from app.hydro_system.models.plant import Plant


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


hydro_batch_client = HydroBatchClient()