# app/ai_vision/services/plant_service.py
from sqlalchemy.orm import Session
from typing import List, Optional
from app.ai_vision.models.plant import VisionPlant, VisionCamera
from app.ai_vision.repositories.plant_repository import plant_repository, camera_repository
from app.ai_vision.integrations.hydro_batch_client import hydro_batch_client
from fastapi import HTTPException, status

class PlantService:
    def create_plant(self, db: Session, **kwargs) -> VisionPlant:
        return plant_repository.create(db, **kwargs)

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
            return existing

        info = hydro_batch_client.get_batch_with_plant(db, hydro_batch_id)
        if not info:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Hydro batch {hydro_batch_id} not found")

        return plant_repository.create(
            db,
            species=info["species"],
            location=None,
            hydro_plant_id=info["plant_id"],
            hydro_batch_id=info["batch_id"],
            status="growing",
            client_id=client_id,
        )

    def create_camera(self, db: Session, **kwargs) -> VisionCamera:
        return camera_repository.create(db, **kwargs)

    def get_all_cameras(self, db: Session) -> List[VisionCamera]:
        return camera_repository.get_all(db)

    # ✅ NEW
    def get_all_cameras_by_client(self, db: Session, client_id: str) -> List[VisionCamera]:
        return camera_repository.get_all_by_client(db, client_id)


plant_service = PlantService()
