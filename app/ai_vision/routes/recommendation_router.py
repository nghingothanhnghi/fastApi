# app/ai_vision/routes/recommendation_router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.user.utils.token import get_current_user
from app.user.models.user import User
from app.ai_vision.models.ai_recommendation import AIRecommendation
from app.ai_vision.services.plant_service import plant_service
from app.ai_vision.services.recommendation_service import recommendation_service
from app.ai_vision.helpers.access_helper import ensure_plant_access
from app.ai_vision.schemas.recommendation_schema import AIRecommendationOut, RecommendationStatusUpdate

router = APIRouter(prefix="/api/v1/plants", tags=["AI Vision - Recommendations"])


@router.get("/{plant_id}/recommendations", response_model=List[AIRecommendationOut])
def get_recommendations(
    plant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plant = plant_service.get_plant(db, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    ensure_plant_access(plant, current_user)

    return (
        db.query(AIRecommendation)
        .filter(AIRecommendation.plant_id == plant_id)
        .order_by(AIRecommendation.created_at.desc())
        .all()
    )


@router.patch(
    "/{plant_id}/recommendations/{recommendation_id}/status",
    response_model=AIRecommendationOut,
)
def update_recommendation_status(
    plant_id: int,
    recommendation_id: int,
    payload: RecommendationStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plant = plant_service.get_plant(db, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    ensure_plant_access(plant, current_user)

    rec = recommendation_service.update_status(
        db, plant_id, recommendation_id, payload.status
    )
    if not rec:
        raise HTTPException(404, "Recommendation not found")
    return rec
