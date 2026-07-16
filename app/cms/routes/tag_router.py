# app/cms/routes/tag_router.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.user.utils.role_requirements import require_roles
from app.user.enums.role_enum import RoleEnum
from app.cms.schemas.tag import TagCreate, TagOut
from app.cms.controllers.tag_controller import tag_controller

router = APIRouter(prefix="/cms/tags", tags=["CMS - Tags"])


@router.get("", response_model=List[TagOut])
def list_tags(db: Session = Depends(get_db)):
    return tag_controller.get_all_tags(db)


@router.post("", response_model=TagOut, status_code=201)
def create_tag(
    data: TagCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MODERATOR)),
):
    return tag_controller.create_tag(db, data)


@router.delete("/{tag_id}")
def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleEnum.ADMIN)),
):
    return tag_controller.delete_tag(db, tag_id)
