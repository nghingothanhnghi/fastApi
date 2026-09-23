# app/ai_vision/services/growth_prediction_service.py
from datetime import datetime, timedelta, time
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.ai_vision.models.growth_prediction import PlantGrowthPrediction
from app.ai_vision.models.plant_growth import PlantGrowthRecord
from app.ai_vision.models.plant import VisionPlant
from app.ai_vision.integrations.hydro_batch_client import hydro_batch_client
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class GrowthPredictionService:
    """
    V5: projects future canopy growth and (when the plant is batch-linked)
    a growth-adjusted stage-transition date. Pure forecast — no commit here;
    the pipeline controller owns the transaction, matching growth_service /
    health_service / anomaly_service.
    """

    DEFAULT_HORIZON_DAYS = 7
    MIN_SAMPLES_FOR_TREND = 2
    TREND_SAMPLE_WINDOW = 5

    def predict_growth(
        self,
        db: Session,
        plant: VisionPlant,
        growth_record: PlantGrowthRecord,
        horizon_days: Optional[int] = None,
    ) -> Optional[PlantGrowthPrediction]:
        horizon_days = horizon_days or self.DEFAULT_HORIZON_DAYS
        reasons: List[str] = []

        recent = (
            db.query(PlantGrowthRecord)
            .filter(
                PlantGrowthRecord.plant_id == plant.id,
                PlantGrowthRecord.growth_rate_pct_per_day.isnot(None),
            )
            .order_by(PlantGrowthRecord.created_at.desc())
            .limit(self.TREND_SAMPLE_WINDOW)
            .all()
        )
        rates = [r.growth_rate_pct_per_day for r in recent]
        sample_count = len(rates)

        if sample_count < self.MIN_SAMPLES_FOR_TREND:
            basis_rate = rates[0] if rates else growth_record.growth_rate_pct_per_day
            variance = None
            reasons.append(
                f"Only {sample_count} usable growth reading(s) available; "
                f"projection based on a single rate, low confidence"
            )
        else:
            basis_rate = round(sum(rates) / sample_count, 4)
            variance = round(sum((r - basis_rate) ** 2 for r in rates) / sample_count, 4)
            reasons.append(
                f"Projected from trailing average growth rate {basis_rate}%/day "
                f"across {sample_count} recent readings (variance={variance})"
            )

        target_date = datetime.utcnow() + timedelta(days=horizon_days)

        predicted_canopy = None
        predicted_growth_pct = None
        if growth_record.canopy_area_px and basis_rate is not None:
            predicted_growth_pct = round(basis_rate * horizon_days, 2)
            predicted_canopy = round(
                growth_record.canopy_area_px * (1 + predicted_growth_pct / 100), 2
            )
            reasons.append(
                f"Canopy area projected from {round(growth_record.canopy_area_px, 1)}px to "
                f"{predicted_canopy}px over {horizon_days} days ({predicted_growth_pct}% total)"
            )
        else:
            reasons.append("No canopy area or growth-rate basis; canopy projection skipped")

        confidence = self._estimate_confidence(sample_count, variance)

        stage_info = self._project_stage_transition(db, plant, growth_record, reasons)

        prediction = PlantGrowthPrediction(
            plant_id=plant.id,
            growth_record_id=growth_record.id,
            horizon_days=horizon_days,
            target_date=target_date,
            basis_growth_rate_pct_per_day=basis_rate,
            basis_sample_count=sample_count,
            basis_variance=variance,
            predicted_canopy_area_px=predicted_canopy,
            predicted_growth_pct=predicted_growth_pct,
            confidence=confidence,
            reasons=reasons,
            **stage_info,
        )
        db.add(prediction)
        db.flush()

        logger.info(
            "Growth prediction computed",
            extra={"plant_id": plant.id, "horizon_days": horizon_days, "confidence": confidence},
        )
        return prediction

    @staticmethod
    def _estimate_confidence(sample_count: int, variance: Optional[float]) -> float:
        if sample_count == 0:
            return 0.1
        base = min(0.3 + sample_count * 0.12, 0.85)
        if variance is not None and variance > 0:
            penalty = min(variance / 100, 0.3)
            base = max(base - penalty, 0.15)
        return round(base, 2)

    def _project_stage_transition(
        self,
        db: Session,
        plant: VisionPlant,
        growth_record: PlantGrowthRecord,
        reasons: List[str],
    ) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "current_stage_id": None,
            "current_stage_name": None,
            "scheduled_stage_transition_date": None,
            "projected_stage_transition_date": None,
            "stage_transition_delta_days": None,
        }

        if not plant.hydro_batch_id:
            reasons.append("Plant is not linked to a hydro batch; stage-transition projection skipped")
            return info

        timeline = hydro_batch_client.get_batch_growth_timeline(db, plant.hydro_batch_id)
        if not timeline or not timeline.get("start_date") or timeline.get("current_stage_day_end") is None:
            reasons.append("No active batch stage window found; stage-transition projection skipped")
            return info

        start_date = timeline["start_date"]
        start_dt = datetime.combine(start_date, time.min) if not isinstance(start_date, datetime) else start_date
        scheduled_transition = start_dt + timedelta(days=timeline["current_stage_day_end"])

        info["current_stage_id"] = timeline["current_stage_id"]
        info["current_stage_name"] = timeline["current_stage_name"]
        info["scheduled_stage_transition_date"] = scheduled_transition

        growth_rate = growth_record.growth_rate_pct_per_day
        baseline_rate = growth_record.baseline_growth_rate_pct_per_day

        if growth_rate is None or not baseline_rate:
            reasons.append(
                "No comparable baseline growth rate; scheduled stage-transition date used unadjusted"
            )
            info["projected_stage_transition_date"] = scheduled_transition
            info["stage_transition_delta_days"] = 0.0
            return info

        pace_ratio = max(growth_rate / baseline_rate, 0.1) if baseline_rate != 0 else 1.0
        remaining_scheduled_days = max((scheduled_transition - datetime.utcnow()).days, 0)
        adjusted_remaining_days = round(remaining_scheduled_days / pace_ratio, 1)
        projected_transition = datetime.utcnow() + timedelta(days=adjusted_remaining_days)
        delta_days = round((projected_transition - scheduled_transition).total_seconds() / 86400, 1)

        info["projected_stage_transition_date"] = projected_transition
        info["stage_transition_delta_days"] = delta_days

        if delta_days > 1:
            reasons.append(
                f"Growth pace ({round(growth_rate, 3)}%/day) is behind baseline "
                f"({round(baseline_rate, 3)}%/day); stage transition projected {delta_days} day(s) later than scheduled"
            )
        elif delta_days < -1:
            reasons.append(
                f"Growth pace ({round(growth_rate, 3)}%/day) is ahead of baseline "
                f"({round(baseline_rate, 3)}%/day); stage transition projected {abs(delta_days)} day(s) earlier than scheduled"
            )
        else:
            reasons.append("Growth pace is on track with baseline; stage transition on schedule")

        return info


growth_prediction_service = GrowthPredictionService()