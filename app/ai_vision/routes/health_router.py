# app/ai_vision/routes/health_router.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.ai_vision.models.plant_health import PlantHealthRecord
from app.ai_vision.models.plant_growth import PlantGrowthRecord
from app.ai_vision.models.plant_anomaly import PlantAnomaly
from app.ai_vision.schemas.health_schema import PlantHealthOut
from app.ai_vision.schemas.growth_schema import PlantGrowthOut
from app.ai_vision.schemas.anomaly_schema import PlantAnomalyOut

router = APIRouter(prefix="/api/v1/plants", tags=["AI Vision - Health & Growth"])


@router.get("/{plant_id}/health", response_model=PlantHealthOut)
def get_latest_health(plant_id: int, db: Session = Depends(get_db)):
    record = (
        db.query(PlantHealthRecord)
        .filter(PlantHealthRecord.plant_id == plant_id)
        .order_by(PlantHealthRecord.created_at.desc())
        .first()
    )
    return record


@router.get("/{plant_id}/growth", response_model=List[PlantGrowthOut])
def get_growth_history(plant_id: int, limit: int = Query(50, le=500), db: Session = Depends(get_db)):
    return (
        db.query(PlantGrowthRecord)
        .filter(PlantGrowthRecord.plant_id == plant_id)
        .order_by(PlantGrowthRecord.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/{plant_id}/anomalies", response_model=List[PlantAnomalyOut])
def get_anomalies(plant_id: int, db: Session = Depends(get_db)):
    return (
        db.query(PlantAnomaly)
        .filter(PlantAnomaly.plant_id == plant_id)
        .order_by(PlantAnomaly.detected_at.desc())
        .all()
    )
