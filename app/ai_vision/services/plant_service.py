# app/ai_vision/services/plant_service.py
from sqlalchemy.orm import Session
from typing import List, Optional
from fastapi import HTTPException, status

from app.ai_vision.models.plant import VisionPlant, VisionCamera
from app.ai_vision.repositories.plant_repository import plant_repository, camera_repository
from app.ai_vision.integrations.hydro_batch_client import hydro_batch_client

# hydro batch status -> VisionPlant status (only applied while still "growing")
_BATCH_TO_PLANT_STATUS = {"harvested": "harvested", "failed": "removed"}


class PlantService:
    # ── hydro alignment ──────────────────────────────────────────────────
    def _apply_hydro_defaults(self, db: Session, data: dict) -> dict:
        batch_id = data.get("hydro_batch_id")
        if batch_id:
            info = hydro_batch_client.get_batch_with_plant(db, batch_id)
            if not info:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"Hydro batch {batch_id} not found")
            data["hydro_plant_id"] = info["plant_id"]  # never trust a mismatching client value
            if not data.get("location"):
                data["location"] = info["zone_location"]
        if not data.get("location") and data.get("camera_id"):
            camera = camera_repository.get(db, data["camera_id"])
            if camera:
                data["location"] = camera.location
        return data

    def sync_from_hydro(self, db: Session, plant: VisionPlant) -> VisionPlant:
        """Backfill location and follow batch lifecycle. Flush only - the
        caller owns the commit (pipeline controller or route)."""
        if not plant.hydro_batch_id:
            return plant
        info = hydro_batch_client.get_batch_with_plant(db, plant.hydro_batch_id)
        if not info:
            return plant
        if not plant.location and info.get("zone_location"):
            plant.location = info["zone_location"]
        mapped = _BATCH_TO_PLANT_STATUS.get(info["status"])
        if mapped and plant.status == "growing":  # respects manual status changes
            plant.status = mapped
        db.flush()
        return plant

    # ── plants ───────────────────────────────────────────────────────────
    def create_plant(self, db: Session, **kwargs) -> VisionPlant:
        return plant_repository.create(db, **self._apply_hydro_defaults(db, dict(kwargs)))

    def get_plant(self, db: Session, plant_id: int) -> Optional[VisionPlant]:
        return plant_repository.get(db, plant_id)

    def get_all_plants(self, db: Session, status: Optional[str] = None) -> List[VisionPlant]:
        return plant_repository.get_all(db, status)

    def get_all_plants_by_client(self, db: Session, client_id: str, status: Optional[str] = None) -> List[VisionPlant]:
        return plant_repository.get_all_by_client(db, client_id, status)

    def update_plant(self, db: Session, plant_id: int, updates: dict) -> Optional[VisionPlant]:
        return plant_repository.update(db, plant_id, updates)

    def get_by_hydro_batch(self, db: Session, hydro_batch_id: int) -> Optional[VisionPlant]:
        return plant_repository.get_by_hydro_batch_id(db, hydro_batch_id)

    def link_or_create_from_hydro_batch(self, db: Session, hydro_batch_id: int, client_id: Optional[str]) -> VisionPlant:
        existing = self.get_by_hydro_batch(db, hydro_batch_id)
        if existing:
            self.sync_from_hydro(db, existing)
            db.commit()
            db.refresh(existing)
            return existing

        info = hydro_batch_client.get_batch_with_plant(db, hydro_batch_id)
        if not info:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Hydro batch {hydro_batch_id} not found")

        return plant_repository.create(
            db,
            species=info["species"],
            location=info["zone_location"],      # <- was None: caused cross-device sensor averaging
            hydro_plant_id=info["plant_id"],
            hydro_batch_id=info["batch_id"],
            status="growing",
            client_id=client_id,
        )

    # ── cameras ──────────────────────────────────────────────────────────
    def create_camera(self, db: Session, **kwargs) -> VisionCamera:
        return camera_repository.create(db, **kwargs)

    def get_all_cameras(self, db: Session) -> List[VisionCamera]:
        return camera_repository.get_all(db)

    def get_all_cameras_by_client(self, db: Session, client_id: str) -> List[VisionCamera]:
        return camera_repository.get_all_by_client(db, client_id)


plant_service = PlantService()