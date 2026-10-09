# app/billiard/services/pricing_rule_service.py
# CRUD for PricingRule. Deleting or editing a rule never changes an existing bill:
# sessions copy what they need into pricing_snapshot at start.
# Services flush; routes commit.
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billiard.models import BilliardTable, PricingRule
from app.billiard.schemas.pricing import (
    PricingRuleCreate, PricingRuleUpdate, normalize_params,
)
from app.billiard.services.table_service import scope_tables
from app.user.models.user import User


def _scope(stmt, user: User):
    """Tenant isolation: SUPER_ADMIN sees all, everyone else only their client_id."""
    if user.is_super_admin():
        return stmt
    return stmt.where(PricingRule.client_id == user.client_id)


def _check_table(db: Session, table_id: int, user: User) -> None:
    found = db.execute(
        scope_tables(select(BilliardTable.id).where(BilliardTable.id == table_id), user)
    ).first()
    if not found:
        raise HTTPException(404, "Billiard table not found")


class PricingRuleService:

    @staticmethod
    def list_rules(db: Session, user: User) -> list[PricingRule]:
        stmt = _scope(select(PricingRule).order_by(PricingRule.priority.desc(), PricingRule.id), user)
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def get_rule(db: Session, rule_id: int, user: User) -> PricingRule:
        rule = db.execute(_scope(select(PricingRule).where(PricingRule.id == rule_id), user)).scalar_one_or_none()
        if not rule:
            raise HTTPException(404, "Pricing rule not found")   # 404 for other tenants too
        return rule

    @staticmethod
    def create_rule(db: Session, data: PricingRuleCreate, user: User) -> PricingRule:
        if data.table_id is not None:
            _check_table(db, data.table_id, user)
        rule = PricingRule(client_id=user.client_id, **data.model_dump())
        db.add(rule)
        db.flush()
        return rule

    @staticmethod
    def update_rule(db: Session, rule_id: int, data: PricingRuleUpdate, user: User) -> PricingRule:
        rule = PricingRuleService.get_rule(db, rule_id, user)
        changes = data.model_dump(exclude_unset=True)

        if changes.get("table_id") is not None:
            _check_table(db, changes["table_id"], user)

        # Validate the MERGED result so partial updates can't create an invalid rule.
        start = changes.get("start_time", rule.start_time)
        end = changes.get("end_time", rule.end_time)
        if (start is None) != (end is None):
            raise HTTPException(422, "start_time and end_time must be given together")

        rule_type = changes.get("rule_type", rule.rule_type)
        try:
            changes["params"] = normalize_params(rule_type, changes.get("params", rule.params))
        except ValueError as e:
            raise HTTPException(422, str(e))

        for field, value in changes.items():
            setattr(rule, field, value)
        db.flush()
        return rule

    @staticmethod
    def delete_rule(db: Session, rule_id: int, user: User) -> None:
        db.delete(PricingRuleService.get_rule(db, rule_id, user))
        db.flush()


pricing_rule_service = PricingRuleService()