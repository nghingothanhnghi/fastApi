# app/ai_vision/routes/health_router.py
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.user.utils.token import get_current_user
from app.user.models.user import User
from app.ai_vision.models.plant_health import PlantHealthRecord
from app.ai_vision.models.plant_growth import PlantGrowthRecord
from app.ai_vision.models.plant_anomaly import PlantAnomaly
from app.ai_vision.services.plant_service import plant_service
from app.ai_vision.helpers.access_helper import ensure_plant_access
from app.ai_vision.schemas.health_schema import PlantHealthOut
from app.ai_vision.schemas.growth_schema import PlantGrowthOut
from app.ai_vision.schemas.anomaly_schema import PlantAnomalyOut

router = APIRouter(prefix="/api/v1/plants", tags=["AI Vision - Health & Growth"])

def _get_authorized_plant(db: Session, plant_id: int, current_user: User):
    plant = plant_service.get_plant(db, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    ensure_plant_access(plant, current_user)
    return plant

@router.get("/{plant_id}/health", response_model=PlantHealthOut)
def get_latest_health(
    plant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_authorized_plant(db, plant_id, current_user)
    record = (
        db.query(PlantHealthRecord)
        .filter(PlantHealthRecord.plant_id == plant_id)
        .order_by(PlantHealthRecord.created_at.desc())
        .first()
    )
    return record


@router.get("/{plant_id}/growth", response_model=List[PlantGrowthOut])
def get_growth_history(
    plant_id: int,
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_authorized_plant(db, plant_id, current_user)
    return (
        db.query(PlantGrowthRecord)
        .filter(PlantGrowthRecord.plant_id == plant_id)
        .order_by(PlantGrowthRecord.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/{plant_id}/anomalies", response_model=List[PlantAnomalyOut])
def get_anomalies(
    plant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_authorized_plant(db, plant_id, current_user)
    return (
        db.query(PlantAnomaly)
        .filter(PlantAnomaly.plant_id == plant_id)
        .order_by(PlantAnomaly.detected_at.desc())
        .all()
    )
