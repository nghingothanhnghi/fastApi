# app/ai_vision/models/growth_prediction.py
from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, JSON, func
from app.database import Base


class PlantGrowthPrediction(Base):
    """
    V5: growth-trajectory projection derived from a plant's PlantGrowthRecord
    history, plus (when the plant is linked to a hydro batch) a comparison
    of the batch's *scheduled* stage-transition date against a growth-rate-
    adjusted projection.

    Read-only forecast — never feeds any actuator/schedule write path. Same
    safety boundary as AIRecommendation: this is informational, not
    automation. `reasons` is required non-empty for the same explainability
    reason AIRecommendation enforces it.
    """
    __tablename__ = "ai_vision_growth_predictions"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("ai_vision_plants.id"), nullable=False, index=True)
    growth_record_id = Column(Integer, ForeignKey("ai_vision_growth_records.id"), nullable=True)

    horizon_days = Column(Integer, nullable=False)
    target_date = Column(DateTime(timezone=True), nullable=False)

    # Projection basis (trailing growth-rate stats used to project forward)
    basis_growth_rate_pct_per_day = Column(Float, nullable=True)
    basis_sample_count = Column(Integer, nullable=False, default=0)
    basis_variance = Column(Float, nullable=True)

    # Predicted outputs
    predicted_canopy_area_px = Column(Float, nullable=True)
    predicted_growth_pct = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)  # 0-1

    # Stage-transition projection (only populated when plant.hydro_batch_id is set)
    current_stage_id = Column(Integer, nullable=True)
    current_stage_name = Column(String(50), nullable=True)
    scheduled_stage_transition_date = Column(DateTime(timezone=True), nullable=True)
    projected_stage_transition_date = Column(DateTime(timezone=True), nullable=True)
    stage_transition_delta_days = Column(Float, nullable=True)  # + = later than scheduled, - = earlier

    reasons = Column(JSON, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<PlantGrowthPrediction(plant_id={self.plant_id}, horizon={self.horizon_days}d)>"