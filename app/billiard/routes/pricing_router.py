# app/billiard/routes/pricing_router.py  (HTTP only; rules live in services)
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.user.enums.role_enum import RoleEnum
from app.user.models.user import User
from app.user.utils.role_requirements import require_roles
from app.user.utils.token import get_current_user
from app.billiard.models import BilliardTable
from app.billiard.schemas.pricing import (
    PricingQuoteOut, PricingRuleCreate, PricingRuleOut, PricingRuleUpdate,
)
from app.billiard.services.billing_service import billing_service
from app.billiard.services.pricing_rule_service import pricing_rule_service
from app.billiard.services.table_service import scope_tables

router = APIRouter(prefix="/billiard/pricing-rules", tags=["Billiard Pricing"])

_manager = require_roles(RoleEnum.ADMIN, RoleEnum.MANAGER)


@router.get("", response_model=list[PricingRuleOut])
def list_rules(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return pricing_rule_service.list_rules(db, current_user)


@router.get("/quote", response_model=PricingQuoteOut)
def quote(
    table_id: int,
    minutes: int = Query(..., ge=1, le=1440),
    at: Optional[datetime] = Query(None, description="Start time; naive = club-local. Default: now"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """What a session starting at `at` and lasting `minutes` would cost. Writes nothing."""
    table = db.execute(
        scope_tables(select(BilliardTable).where(BilliardTable.id == table_id), current_user)
    ).scalar_one_or_none()
    if not table:
        raise HTTPException(404, "Billiard table not found")
    return billing_service.preview_fee(db, table, at or datetime.now(timezone.utc), minutes)


@router.post("", response_model=PricingRuleOut, status_code=201)
def create_rule(
    data: PricingRuleCreate, db: Session = Depends(get_db), current_user: User = Depends(_manager),
):
    rule = pricing_rule_service.create_rule(db, data, current_user)
    db.commit()
    db.refresh(rule)
    return rule


@router.put("/{rule_id}", response_model=PricingRuleOut)
def update_rule(
    rule_id: int, data: PricingRuleUpdate,
    db: Session = Depends(get_db), current_user: User = Depends(_manager),
):
    rule = pricing_rule_service.update_rule(db, rule_id, data, current_user)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db), current_user: User = Depends(_manager)):
    """Existing bills are unaffected: sessions keep their own pricing snapshot."""
    pricing_rule_service.delete_rule(db, rule_id, current_user)
    db.commit()
    return {"detail": "Pricing rule deleted"}