# app/ai_vision/repositories/plant_repository.py
from sqlalchemy.orm import Session
from typing import List, Optional
from app.ai_vision.models.plant import VisionPlant, VisionCamera


class PlantRepository:
    def create(self, db: Session, **kwargs) -> VisionPlant:
        plant = VisionPlant(**kwargs)
        db.add(plant)
        db.commit()
        db.refresh(plant)
        return plant

    def get(self, db: Session, plant_id: int) -> Optional[VisionPlant]:
        return db.query(VisionPlant).filter(VisionPlant.id == plant_id).first()

    def get_all(self, db: Session, status: Optional[str] = None) -> List[VisionPlant]:
        query = db.query(VisionPlant)
        if status:
            query = query.filter(VisionPlant.status == status)
        return query.order_by(VisionPlant.created_at.desc()).all()

    # ✅ NEW — tenant-scoped listing, mirrors HydroDeviceService.get_devices_by_client
    def get_all_by_client(self, db: Session, client_id: str, status: Optional[str] = None) -> List[VisionPlant]:
        query = db.query(VisionPlant).filter(VisionPlant.client_id == client_id)
        if status:
            query = query.filter(VisionPlant.status == status)
        return query.order_by(VisionPlant.created_at.desc()).all()

    def update(self, db: Session, plant_id: int, updates: dict) -> Optional[VisionPlant]:
        plant = self.get(db, plant_id)
        if not plant:
            return None
        for k, v in updates.items():
            setattr(plant, k, v)
        db.commit()
        db.refresh(plant)
        return plant

    def get_by_hydro_batch_id(self, db: Session, hydro_batch_id: int) -> Optional[VisionPlant]:
        return (
            db.query(VisionPlant)
            .filter(VisionPlant.hydro_batch_id == hydro_batch_id)
            .order_by(VisionPlant.created_at.desc())
            .first()
        )

    def get_by_hydro_plant_id(self, db: Session, hydro_plant_id: int) -> List[VisionPlant]:
        return db.query(VisionPlant).filter(VisionPlant.hydro_plant_id == hydro_plant_id).all()


class CameraRepository:
    def create(self, db: Session, **kwargs) -> VisionCamera:
        camera = VisionCamera(**kwargs)
        db.add(camera)
        db.commit()
        db.refresh(camera)
        return camera

    def get(self, db: Session, camera_id: int) -> Optional[VisionCamera]:
        return db.query(VisionCamera).filter(VisionCamera.id == camera_id).first()

    def get_all(self, db: Session) -> List[VisionCamera]:
        return db.query(VisionCamera).filter(VisionCamera.is_active == True).all()

    # ✅ NEW
    def get_all_by_client(self, db: Session, client_id: str) -> List[VisionCamera]:
        return db.query(VisionCamera).filter(
            VisionCamera.is_active == True,
            VisionCamera.client_id == client_id,
        ).all()

plant_repository = PlantRepository()
camera_repository = CameraRepository()
