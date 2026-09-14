# app/ai_vision/repositories/plant_repository.py
from sqlalchemy.orm import Session
from typing import List, Optional
from app.ai_vision.models.plant import Plant, Camera


class PlantRepository:
    def create(self, db: Session, **kwargs) -> Plant:
        plant = Plant(**kwargs)
        db.add(plant)
        db.commit()
        db.refresh(plant)
        return plant

    def get(self, db: Session, plant_id: int) -> Optional[Plant]:
        return db.query(Plant).filter(Plant.id == plant_id).first()

    def get_all(self, db: Session, status: Optional[str] = None) -> List[Plant]:
        query = db.query(Plant)
        if status:
            query = query.filter(Plant.status == status)
        return query.order_by(Plant.created_at.desc()).all()

    def update(self, db: Session, plant_id: int, updates: dict) -> Optional[Plant]:
        plant = self.get(db, plant_id)
        if not plant:
            return None
        for k, v in updates.items():
            setattr(plant, k, v)
        db.commit()
        db.refresh(plant)
        return plant


class CameraRepository:
    def create(self, db: Session, **kwargs) -> Camera:
        camera = Camera(**kwargs)
        db.add(camera)
        db.commit()
        db.refresh(camera)
        return camera

    def get(self, db: Session, camera_id: int) -> Optional[Camera]:
        return db.query(Camera).filter(Camera.id == camera_id).first()

    def get_all(self, db: Session) -> List[Camera]:
        return db.query(Camera).filter(Camera.is_active == True).all()


plant_repository = PlantRepository()
camera_repository = CameraRepository()
