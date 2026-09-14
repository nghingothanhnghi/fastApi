# app/ai_vision/routes/recommendation_router.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.ai_vision.models.ai_recommendation import AIRecommendation
from app.ai_vision.schemas.recommendation_schema import AIRecommendationOut

router = APIRouter(prefix="/api/v1/plants", tags=["AI Vision - Recommendations"])


@router.get("/{plant_id}/recommendations", response_model=List[AIRecommendationOut])
def get_recommendations(plant_id: int, db: Session = Depends(get_db)):
    return (
        db.query(AIRecommendation)
        .filter(AIRecommendation.plant_id == plant_id)
        .order_by(AIRecommendation.created_at.desc())
        .all()
    )
