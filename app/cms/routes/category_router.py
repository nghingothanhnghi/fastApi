# app/cms/routes/category_router.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.user.utils.role_requirements import require_roles
from app.user.enums.role_enum import RoleEnum
from app.cms.schemas.category import CategoryCreate, CategoryUpdate, CategoryOut
from app.cms.controllers.category_controller import category_controller

router = APIRouter(prefix="/cms/categories", tags=["CMS - Categories"])


@router.get("", response_model=List[CategoryOut])
def list_categories(
    parent_id: Optional[int] = Query(None, description="Filter by parent category id (omit for all)"),
    db: Session = Depends(get_db),
):
    """Public: list categories, optionally filtered by parent (pass parent_id= for a subtree)."""
    return category_controller.get_all_categories(db, parent_id)


@router.get("/{category_id}", response_model=CategoryOut)
def get_category(category_id: int, db: Session = Depends(get_db)):
    return category_controller.get_category(db, category_id)


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(
    data: CategoryCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MODERATOR)),
):
    return category_controller.create_category(db, data)


@router.put("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    data: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MODERATOR)),
):
    return category_controller.update_category(db, category_id, data)


@router.delete("/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleEnum.ADMIN)),
):
    return category_controller.delete_category(db, category_id)
