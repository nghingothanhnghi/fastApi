# app/hydro_system/services/growth_plan_service.py
from sqlalchemy.orm import Session
from typing import List, Optional
from app.hydro_system.models.growth_plan import GrowthPlan
from app.hydro_system.models.plant import Plant
from app.hydro_system.models.plant_batch import PlantBatch
from app.hydro_system.schemas.growth_plan import GrowthPlanCreate


class GrowthPlanService:
    """
    Invariant enforced here (not at DB level): every plant that has at least
    one plan has exactly one plan with is_default=True.
    """

    # ── internal helpers ────────────────────────────────────────────────

    def _clear_other_defaults(self, db: Session, plant_id: int, keep_id: Optional[int] = None) -> None:
        q = db.query(GrowthPlan).filter(
            GrowthPlan.plant_id == plant_id,
            GrowthPlan.is_default == True,  # noqa: E712
        )
        if keep_id is not None:
            q = q.filter(GrowthPlan.id != keep_id)
        q.update({"is_default": False}, synchronize_session=False)

    # ── CRUD ────────────────────────────────────────────────────────────

    def create_plan(self, db: Session, plan_in: GrowthPlanCreate) -> GrowthPlan:
        """
        Raises LookupError if the plant doesn't exist.
        The first plan created for a plant is always the default.
        """
        if not db.query(Plant.id).filter(Plant.id == plan_in.plant_id).first():
            raise LookupError(f"Plant {plan_in.plant_id} not found")

        data = plan_in.dict()
        has_plans = (
            db.query(GrowthPlan.id)
            .filter(GrowthPlan.plant_id == plan_in.plant_id)
            .first()
            is not None
        )
        data["is_default"] = bool(data.get("is_default")) or not has_plans

        try:
            plan = GrowthPlan(**data)
            db.add(plan)
            db.flush()  # need plan.id before clearing the others
            if plan.is_default:
                self._clear_other_defaults(db, plan.plant_id, keep_id=plan.id)
            db.commit()
            db.refresh(plan)
            return plan
        except Exception:
            db.rollback()
            raise

    def get_plan(self, db: Session, plan_id: int) -> Optional[GrowthPlan]:
        return db.query(GrowthPlan).filter(GrowthPlan.id == plan_id).first()

    def get_plans_by_plant(self, db: Session, plant_id: int) -> List[GrowthPlan]:
        return db.query(GrowthPlan).filter(GrowthPlan.plant_id == plant_id).all()

    def get_default_plan_for_plant(self, db: Session, plant_id: int) -> Optional[GrowthPlan]:
        """
        Plan flagged is_default=True; falls back to the earliest plan for
        that plant if (legacy data) none is flagged; None if no plans exist.
        """
        plan = (
            db.query(GrowthPlan)
            .filter(GrowthPlan.plant_id == plant_id, GrowthPlan.is_default == True)  # noqa: E712
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
        """
        Raises ValueError when asked to un-default the plant's only default
        plan (mark a different plan as default instead).
        """
        plan = self.get_plan(db, plan_id)
        if not plan:
            return None

        if updates.get("is_default") is False and plan.is_default:
            raise ValueError(
                "A plant must always have a default plan; "
                "mark another plan as default instead"
            )

        try:
            for key, value in updates.items():
                setattr(plan, key, value)
            db.flush()
            if updates.get("is_default") is True:
                self._clear_other_defaults(db, plan.plant_id, keep_id=plan.id)
            db.commit()
            db.refresh(plan)
            return plan
        except Exception:
            db.rollback()
            raise

    def delete_plan(self, db: Session, plan_id: int) -> bool:
        """
        Raises ValueError if any batch still follows this plan.
        If the deleted plan was the default, the earliest remaining plan
        for the plant is promoted.
        """
        plan = self.get_plan(db, plan_id)
        if not plan:
            return False

        in_use = db.query(PlantBatch.id).filter(PlantBatch.plan_id == plan_id).count()
        if in_use:
            raise ValueError(
                f"Plan is used by {in_use} batch(es); reassign or delete them first"
            )

        plant_id = plan.plant_id
        was_default = plan.is_default

        try:
            db.delete(plan)
            db.flush()
            if was_default:
                successor = (
                    db.query(GrowthPlan)
                    .filter(GrowthPlan.plant_id == plant_id)
                    .order_by(GrowthPlan.id.asc())
                    .first()
                )
                if successor:
                    successor.is_default = True
            db.commit()
            return True
        except Exception:
            db.rollback()
            raise


growth_plan_service = GrowthPlanService()
