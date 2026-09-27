# app/hydro_system/services/growth_plan_service.py
from sqlalchemy.orm import Session
from typing import List, Optional
from app.hydro_system.models.growth_plan import GrowthPlan
from app.hydro_system.schemas.growth_plan import GrowthPlanCreate


class GrowthPlanService:
    def create_plan(self, db: Session, plan_in: GrowthPlanCreate) -> GrowthPlan:
        plan = GrowthPlan(**plan_in.dict())
        db.add(plan)
        db.commit()
        db.refresh(plan)
        return plan

    def get_plan(self, db: Session, plan_id: int) -> Optional[GrowthPlan]:
        return db.query(GrowthPlan).filter(GrowthPlan.id == plan_id).first()

    def get_plans_by_plant(self, db: Session, plant_id: int) -> List[GrowthPlan]:
        return db.query(GrowthPlan).filter(GrowthPlan.plant_id == plant_id).all()

    def get_default_plan_for_plant(self, db: Session, plant_id: int) -> Optional[GrowthPlan]:
        """
        Resolve the plan a batch should use when none is explicitly given.
        Prefers the plan flagged is_default=True; falls back to the
        earliest-created plan for that plant if no default is set; returns
        None if the plant has no plans at all yet.
        """
        plan = (
            db.query(GrowthPlan)
            .filter(GrowthPlan.plant_id == plant_id, GrowthPlan.is_default == True)
            .first()
        )
        if plan:
            return plan
        return (
            db.query(GrowthPlan)
            .filter(GrowthPlan.plant_id == plant_id)
            .order_by(GrowthPlan.id.asc())
            .first()
        )

    def update_plan(self, db: Session, plan_id: int, updates: dict) -> Optional[GrowthPlan]:
        plan = self.get_plan(db, plan_id)
        if not plan:
            return None
        for key, value in updates.items():
            setattr(plan, key, value)
        db.commit()
        db.refresh(plan)
        return plan

    def delete_plan(self, db: Session, plan_id: int) -> bool:
        plan = self.get_plan(db, plan_id)
        if not plan:
            return False
        db.delete(plan)
        db.commit()
        return True


growth_plan_service = GrowthPlanService()