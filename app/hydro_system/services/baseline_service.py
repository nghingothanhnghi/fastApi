# app/hydro_system/services/baseline_service.py
# Configurable baseline/threshold settings per zone (device), mirroring the
# get_for_device()/update_device_thresholds() pattern already used by
# app/hydro_system/services/threshold_service.py — nothing here is hard-coded.

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.hydro_system.models.irrigation import ZoneBaselineSettings
from app.hydro_system.schemas.irrigation import ZoneBaselineUpdate

DEFAULT_EFFICIENCY_THRESHOLD_PERCENT = 20.0


class BaselineService:

    def get_or_create(self, db: Session, zone_id: int) -> ZoneBaselineSettings:
        baseline = (
            db.query(ZoneBaselineSettings)
            .filter(ZoneBaselineSettings.zone_id == zone_id)
            .first()
        )
        if baseline:
            return baseline

        try:
            baseline = ZoneBaselineSettings(
                zone_id=zone_id,
                efficiency_threshold_percent=DEFAULT_EFFICIENCY_THRESHOLD_PERCENT,
            )
            db.add(baseline)
            db.commit()
            db.refresh(baseline)
            return baseline
        except SQLAlchemyError:
            db.rollback()
            raise

    def get(self, db: Session, zone_id: int) -> Optional[ZoneBaselineSettings]:
        return (
            db.query(ZoneBaselineSettings)
            .filter(ZoneBaselineSettings.zone_id == zone_id)
            .first()
        )

    def update(self, db: Session, zone_id: int, data: ZoneBaselineUpdate) -> ZoneBaselineSettings:
        baseline = self.get_or_create(db, zone_id)
        try:
            for field, value in data.model_dump(exclude_unset=True).items():
                setattr(baseline, field, value)
            db.commit()
            db.refresh(baseline)
            return baseline
        except SQLAlchemyError:
            db.rollback()
            raise


baseline_service = BaselineService()
