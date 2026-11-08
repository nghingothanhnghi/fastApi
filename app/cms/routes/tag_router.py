# app/cms/routes/tag_router.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.user.utils.role_requirements import require_roles
from app.user.enums.role_enum import RoleEnum
from app.cms.schemas.tag import TagCreate, TagUpdate, TagOut, TagDeleteOut
from app.cms.controllers.tag_controller import tag_controller

router = APIRouter(prefix="/cms/tags", tags=["CMS - Tags"])


@router.get("", response_model=List[TagOut])
def list_tags(db: Session = Depends(get_db)):
    return tag_controller.get_all_tags(db)


@router.get("/slug/{slug}", response_model=TagOut)
def get_tag_by_slug(slug: str, db: Session = Depends(get_db)):
    """Public: resolve a tag from its URL slug (e.g. for /tags/:slug pages)."""
    return tag_controller.get_tag_by_slug(db, slug)


@router.post("", response_model=TagOut, status_code=201)
def create_tag(
    data: TagCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MODERATOR)),
):
    return tag_controller.create_tag(db, data)


@router.put("/{tag_id}", response_model=TagOut)
def update_tag(
    tag_id: int,
    data: TagUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MODERATOR)),
):
    """Partial update (name and/or slug). 409 on a duplicate name or slug; `null` is a 422."""
    return tag_controller.update_tag(db, tag_id, data)


@router.delete("/{tag_id}", response_model=TagDeleteOut)
def delete_tag(
    tag_id: int,
    force: bool = Query(False, description="Delete even if posts use it (detaches it from them)"),
    merge_into: Optional[int] = Query(None, description="Give posts this tag instead, then delete"),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleEnum.ADMIN)),
):
    """A tag used by posts is refused with 409 unless `force=true` or `merge_into=<tag id>` is given."""
    return tag_controller.delete_tag(db, tag_id, force, merge_into)
