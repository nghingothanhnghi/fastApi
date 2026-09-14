# app/ai_vision/services/growth_service.py
from sqlalchemy.orm import Session
from typing import Optional, List
from app.ai_vision.models.plant_growth import PlantGrowthRecord
from app.ai_vision.models.vision_prediction import VisionPrediction
from app.ai_vision.models.image import PlantImage
from app.ai_vision import config


class GrowthService:
    def record_growth(self, db: Session, image: PlantImage, detection_prediction: VisionPrediction) -> PlantGrowthRecord:
        canopy_area = detection_prediction.raw_output.get("canopy_area_px")

        previous = (
            db.query(PlantGrowthRecord)
            .filter(PlantGrowthRecord.plant_id == image.plant_id)
            .order_by(PlantGrowthRecord.created_at.desc())
            .first()
        )

        growth_pct = None
        growth_rate = None
        deviation_pct = None
        baseline_rate = None

        if previous and previous.canopy_area_px and canopy_area:
            growth_pct = round(((canopy_area - previous.canopy_area_px) / previous.canopy_area_px) * 100, 2)

            days_elapsed = max((image.captured_at - previous.created_at).total_seconds() / 86400, 1 / 24)
            growth_rate = round(growth_pct / days_elapsed, 3)

            baseline_rate = self._get_baseline_rate(db, image.plant_id)
            if baseline_rate is not None:
                if baseline_rate == 0:
                    # Both flat -> genuinely no deviation. Nonzero growth off
                    # a zero baseline is mathematically undefined as a
                    # percentage (would be division by zero) - report None
                    # rather than crash or silently lie with 0/inf.
                    deviation_pct = 0.0 if growth_rate == 0 else None
                else:
                    deviation_pct = round(((growth_rate - baseline_rate) / baseline_rate) * 100, 2)

        record = PlantGrowthRecord(
            plant_id=image.plant_id,
            image_id=image.id,
            canopy_area_px=canopy_area,
            growth_pct_since_last=growth_pct,
            growth_rate_pct_per_day=growth_rate,
            baseline_growth_rate_pct_per_day=baseline_rate,
            deviation_from_baseline_pct=deviation_pct,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def _get_baseline_rate(self, db: Session, plant_id: int) -> Optional[float]:
        """Baseline = plant's own expected_growth_profile if set, else the
        trailing average of its last 5 growth_rate readings. Configurable,
        never hard-coded, per the brief."""
        from app.ai_vision.models.plant import VisionPlant

        plant = db.query(VisionPlant).filter(VisionPlant.id == plant_id).first()
        if plant and plant.expected_growth_profile:
            configured = plant.expected_growth_profile.get("canopy_growth_pct_per_day")
            if configured is not None:
                return configured

        recent: List[PlantGrowthRecord] = (
            db.query(PlantGrowthRecord)
            .filter(PlantGrowthRecord.plant_id == plant_id, PlantGrowthRecord.growth_rate_pct_per_day.isnot(None))
            .order_by(PlantGrowthRecord.created_at.desc())
            .limit(5)
            .all()
        )
        rates = [r.growth_rate_pct_per_day for r in recent]
        return round(sum(rates) / len(rates), 3) if rates else None

    def is_growth_anomalous(self, deviation_from_baseline_pct: Optional[float]) -> bool:
        if deviation_from_baseline_pct is None:
            return False
        return abs(deviation_from_baseline_pct) / 100 >= config.GROWTH_ANOMALY_THRESHOLD


growth_service = GrowthService()
