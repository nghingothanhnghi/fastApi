# app/ai_vision/routes/prediction_router.py
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.user.utils.token import get_current_user
from app.user.models.user import User
from app.ai_vision.models.growth_prediction import PlantGrowthPrediction
from app.ai_vision.services.plant_service import plant_service
from app.ai_vision.helpers.access_helper import ensure_plant_access
from app.ai_vision.schemas.growth_prediction_schema import PlantGrowthPredictionOut

router = APIRouter(prefix="/api/v1/plants", tags=["AI Vision - Growth Prediction"])


@router.get("/{plant_id}/growth-predictions", response_model=List[PlantGrowthPredictionOut])
def get_growth_predictions(
    plant_id: int,
    limit: int = Query(20, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plant = plant_service.get_plant(db, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    ensure_plant_access(plant, current_user)

    return (
        db.query(PlantGrowthPrediction)
        .filter(PlantGrowthPrediction.plant_id == plant_id)
        .order_by(PlantGrowthPrediction.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/{plant_id}/growth-predictions/latest", response_model=PlantGrowthPredictionOut)
def get_latest_growth_prediction(
    plant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plant = plant_service.get_plant(db, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    ensure_plant_access(plant, current_user)

    prediction = (
        db.query(PlantGrowthPrediction)
        .filter(PlantGrowthPrediction.plant_id == plant_id)
        .order_by(PlantGrowthPrediction.created_at.desc())
        .first()
    )
    if not prediction:
        raise HTTPException(404, "No growth prediction available yet")
    return prediction