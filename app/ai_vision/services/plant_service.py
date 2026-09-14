# app/ai_vision/services/plant_service.py
from sqlalchemy.orm import Session
from typing import List, Optional
from app.ai_vision.repositories.plant_repository import plant_repository, camera_repository
from app.ai_vision.models.plant import VisionPlant, VisionCamera


class PlantService:
    def create_plant(self, db: Session, **kwargs) -> VisionPlant:
        return plant_repository.create(db, **kwargs)

    def get_plant(self, db: Session, plant_id: int) -> Optional[VisionPlant]:
        return plant_repository.get(db, plant_id)

    def get_all_plants(self, db: Session, status: Optional[str] = None) -> List[VisionPlant]:
        return plant_repository.get_all(db, status)

    def update_plant(self, db: Session, plant_id: int, updates: dict) -> Optional[VisionPlant]:
        return plant_repository.update(db, plant_id, updates)

    def create_camera(self, db: Session, **kwargs) -> VisionCamera:
        return camera_repository.create(db, **kwargs)

    def get_all_cameras(self, db: Session) -> List[VisionCamera]:
        return camera_repository.get_all(db)


plant_service = PlantService()
