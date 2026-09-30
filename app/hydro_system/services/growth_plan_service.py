# app/hydro_system/services/growth_plan_service.py
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Dict, List, Optional

from app.hydro_system.models.growth_plan import GrowthPlan
from app.hydro_system.models.growth_stage import GrowthStage
from app.hydro_system.models.growth_recipe import GrowthRecipe
from app.hydro_system.models.plant import Plant
from app.hydro_system.models.plant_batch import PlantBatch
from app.hydro_system.schemas.growth_plan import GrowthPlanCreate


class PlanNameConflictError(Exception):
    """Another plan of the same plant already uses this name."""


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

    def _assert_unique_name(
        self, db: Session, plant_id: int, name: str, exclude_id: Optional[int] = None
    ) -> None:
        q = db.query(GrowthPlan.id).filter(
            GrowthPlan.plant_id == plant_id,
            func.lower(GrowthPlan.name) == name.strip().lower(),
        )
        if exclude_id is not None:
            q = q.filter(GrowthPlan.id != exclude_id)
        if q.first():
            raise PlanNameConflictError(f"A plan named '{name}' already exists for this plant")

    # ── batch counts ────────────────────────────────────────────────────

    def get_batch_counts(self, db: Session, plan_ids: List[int]) -> Dict[int, int]:
        """{plan_id: number of batches following it}, in ONE grouped query."""
        if not plan_ids:
            return {}
        rows = (
            db.query(PlantBatch.plan_id, func.count(PlantBatch.id))
            .filter(PlantBatch.plan_id.in_(plan_ids))
            .group_by(PlantBatch.plan_id)
            .all()
        )
        return {plan_id: count for plan_id, count in rows}

    # ── CRUD ────────────────────────────────────────────────────────────

    def create_plan(self, db: Session, plan_in: GrowthPlanCreate) -> GrowthPlan:
        """
        Raises LookupError if the plant doesn't exist, PlanNameConflictError
        on a duplicate name. The first plan created for a plant is always
        the default.
        """
        if not db.query(Plant.id).filter(Plant.id == plan_in.plant_id).first():
            raise LookupError(f"Plant {plan_in.plant_id} not found")

        self._assert_unique_name(db, plan_in.plant_id, plan_in.name)

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
        plan, PlanNameConflictError on a duplicate name.
        """
        plan = self.get_plan(db, plan_id)
        if not plan:
            return None

        if updates.get("is_default") is False and plan.is_default:
            raise ValueError(
                "A plant must always have a default plan; "
                "mark another plan as default instead"
            )

        if updates.get("name"):
            self._assert_unique_name(db, plan.plant_id, updates["name"], exclude_id=plan.id)

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

    def duplicate_plan(
        self, db: Session, plan_id: int, new_name: Optional[str] = None
    ) -> Optional[GrowthPlan]:
        """
        Deep copy: plan + all its stages + all their recipes, in one
        transaction. The copy is never the default (keeps the
        one-default-per-plant invariant) and starts with 0 batches.
        Returns None if the source plan doesn't exist. If new_name is given
        and already taken, raises PlanNameConflictError; if omitted, a free
        "<name> (copy)" / "<name> (copy) 2" ... is generated.
        """
        src = self.get_plan(db, plan_id)
        if not src:
            return None

        if new_name:
            self._assert_unique_name(db, src.plant_id, new_name)
            name = new_name.strip()
        else:
            existing = {
                n.lower() for (n,) in db.query(GrowthPlan.name)
                .filter(GrowthPlan.plant_id == src.plant_id).all()
            }
            base = f"{src.name} (copy)"
            name, i = base, 2
            while name.lower() in existing:
                name, i = f"{base} {i}", i + 1

        try:
            new_plan = GrowthPlan(
                plant_id=src.plant_id,
                name=name,
                description=src.description,
                is_default=False,
            )
            db.add(new_plan)
            db.flush()  # need new_plan.id

            src_stages = (
                db.query(GrowthStage)
                .filter(GrowthStage.plan_id == src.id)
                .order_by(GrowthStage.day_start.asc())
                .all()
            )
            for s in src_stages:
                new_stage = GrowthStage(
                    plan_id=new_plan.id,
                    plant_id=s.plant_id,
                    name=s.name,
                    day_start=s.day_start,
                    day_end=s.day_end,
                )
                db.add(new_stage)
                db.flush()  # need new_stage.id for the recipes
                for r in s.recipes:
                    db.add(GrowthRecipe(
                        stage_id=new_stage.id,
                        actuator_type=r.actuator_type,
                        action=r.action,
                        start_time=r.start_time,
                        end_time=r.end_time,
                        interval_on_min=r.interval_on_min,
                        interval_off_min=r.interval_off_min,
                    ))

            db.commit()
            db.refresh(new_plan)
            return new_plan
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