# app/hydro_system/services/growth_stage_service.py
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from app.hydro_system.models.growth_recipe import GrowthRecipe
from app.hydro_system.models.growth_stage import GrowthStage
from app.hydro_system.models.plant_batch import PlantBatch
from app.hydro_system.schemas.growth_stage import GrowthStageCreate, GrowthStageWithRecipesUpdate
from app.hydro_system.services.growth_plan_service import growth_plan_service
from app.hydro_system.services.growth_recipe_service import growth_recipe_service

class StageRangeError(ValueError):
    """Stage day range is invalid or overlaps another stage in the same plan."""


class StageInUseError(ValueError):
    """Stage is still referenced by one or more batches."""

class GrowthStageService:

    # ── validation helpers ──────────────────────────────────────────────

    def _assert_valid_range(self, day_start: int, day_end: int) -> None:
        if day_start < 0 or day_end < day_start:
            raise StageRangeError("day_end must be >= day_start and both must be >= 0")

    def _assert_no_overlap(
        self,
        db: Session,
        plan_id: Optional[int],
        day_start: int,
        day_end: int,
        exclude_id: Optional[int] = None,
    ) -> None:
        # Legacy stages without a plan can't be compared meaningfully.
        if plan_id is None:
            return
        q = db.query(GrowthStage).filter(
            GrowthStage.plan_id == plan_id,
            GrowthStage.day_start <= day_end,
            GrowthStage.day_end >= day_start,
        )
        if exclude_id is not None:
            q = q.filter(GrowthStage.id != exclude_id)
        clash = q.first()
        if clash:
            raise StageRangeError(
                f"Days {day_start}-{day_end} overlap stage '{clash.name}' "
                f"({clash.day_start}-{clash.day_end})"
            )

    def get_plan_issues(self, db: Session, plan_id: int) -> dict:
        """
        Report-only check of a whole plan. Gaps are warnings (building a plan
        stage by stage creates temporary gaps); overlaps should not exist
        after this change but may exist in legacy data.
        """
        stages = self.get_stages_by_plan(db, plan_id)
        gaps, overlaps = [], []
        for prev, nxt in zip(stages, stages[1:]):
            if nxt.day_start > prev.day_end + 1:
                gaps.append({
                    "after_stage": prev.name,
                    "before_stage": nxt.name,
                    "from_day": prev.day_end + 1,
                    "to_day": nxt.day_start - 1,
                })
            elif nxt.day_start <= prev.day_end:
                overlaps.append({
                    "stage_a": prev.name,
                    "stage_b": nxt.name,
                    "from_day": nxt.day_start,
                    "to_day": min(prev.day_end, nxt.day_end),
                })
        return {"plan_id": plan_id, "stage_count": len(stages), "gaps": gaps, "overlaps": overlaps}

    # ── CRUD ────────────────────────────────────────────────────────────

    def create_stage(self, db: Session, stage_in: GrowthStageCreate) -> GrowthStage:
        # ✅ plant_id is derived from the plan, not passed in directly, so a
        # stage can never be created under a plan/plant mismatch.
        plan = growth_plan_service.get_plan(db, stage_in.plan_id)
        if not plan:
            raise LookupError(f"Growth plan {stage_in.plan_id} not found")

        self._assert_no_overlap(db, plan.id, stage_in.day_start, stage_in.day_end)

        stage = GrowthStage(
            plan_id=plan.id,
            plant_id=plan.plant_id,
            **stage_in.dict(exclude={"plan_id"}),
        )
        db.add(stage)
        db.commit()
        db.refresh(stage)
        return stage    

    def get_stage(self, db: Session, stage_id: int) -> Optional[GrowthStage]:
        return db.query(GrowthStage).filter(GrowthStage.id == stage_id).first()

    def get_stages_by_plant(self, db: Session, plant_id: int):        
        """
        Admin / back-compat listing across ALL plans of a plant. Progression
        logic must use get_stages_by_plan instead.
        """        
        return (
            db.query(GrowthStage)
            .options(joinedload(GrowthStage.recipes))
            .filter(GrowthStage.plant_id == plant_id)
            .all()
        )

    def get_stages_by_plan(self, db: Session, plan_id: int):
        return (
            db.query(GrowthStage)
            .options(joinedload(GrowthStage.recipes))
            .filter(GrowthStage.plan_id == plan_id)
            .order_by(GrowthStage.day_start.asc())
            .all()
        )    
    
    def update_stage(self, db: Session, stage_id: int, updates: dict) -> Optional[GrowthStage]:
        stage = self.get_stage(db, stage_id)
        if not stage:
            return None

        # Merge existing + incoming so partial updates are validated too.
        new_start = updates.get("day_start", stage.day_start)
        new_end = updates.get("day_end", stage.day_end)
        self._assert_valid_range(new_start, new_end)
        self._assert_no_overlap(db, stage.plan_id, new_start, new_end, exclude_id=stage.id)

        for key, value in updates.items():
            setattr(stage, key, value)
        db.commit()
        db.refresh(stage)
        return stage

    def update_stage_with_recipes(
        self,
        db: Session,
        stage_id: int,
        data: GrowthStageWithRecipesUpdate
    ) -> Optional[GrowthStage]:
        stage = self.get_stage(db, stage_id)
        if not stage:
            return None

        # Validate BEFORE touching anything so a rejected update leaves the
        # stage and its recipes exactly as they were.
        self._assert_valid_range(data.day_start, data.day_end)
        self._assert_no_overlap(db, stage.plan_id, data.day_start, data.day_end, exclude_id=stage.id)

        try:
            stage.name = data.name
            stage.day_start = data.day_start
            stage.day_end = data.day_end

            db.query(GrowthRecipe).filter(GrowthRecipe.stage_id == stage_id).delete()
            for r in data.recipes:
                growth_recipe_service.validate_target(db, r.actuator_type, r.actuator_id)
                db.add(GrowthRecipe(**r.dict(), stage_id=stage_id))

            db.commit()
            db.refresh(stage)
            return stage
        except Exception:
            db.rollback()
            raise

    def delete_stage(self, db: Session, stage_id: int) -> bool:
        stage = self.get_stage(db, stage_id)
        if not stage:
            return False

        in_use = db.query(PlantBatch.id).filter(PlantBatch.current_stage_id == stage_id).count()
        if in_use:
            raise StageInUseError(
                f"Stage is the current stage of {in_use} batch(es); "
                f"move or delete them first"
            )

        db.delete(stage)
        db.commit()
        return True

growth_stage_service = GrowthStageService()
