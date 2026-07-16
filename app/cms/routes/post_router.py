# app/cms/routes/post_router.py
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.user.utils.token import get_current_user
from app.user.enums.role_enum import RoleEnum
from app.user.models.user import User
from app.cms.models.post import PostStatus, PostType
from app.cms.schemas.post import PostCreate, PostUpdate, PostOut, PaginatedPosts
from app.cms.controllers.post_controller import post_controller

router = APIRouter(prefix="/cms/posts", tags=["CMS - Posts"])


def _ensure_owner_or_editor(post, current_user: User) -> None:
    """Author of the post, or ADMIN/SUPER_ADMIN/MODERATOR, may modify it."""
    is_editor = (
        current_user.has_role(RoleEnum.SUPER_ADMIN)
        or current_user.has_role(RoleEnum.ADMIN)
        or current_user.has_role(RoleEnum.MODERATOR)
    )
    if post.author_id != current_user.id and not is_editor:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to modify this post")


@router.post("", response_model=PostOut, status_code=201)
def create_post(
    data: PostCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a post/page. `featured_image_id` should come from POST /cms/media/upload."""
    return post_controller.create_post(db, data, current_user.id)


@router.get("", response_model=PaginatedPosts)
def list_posts(
    status_filter: Optional[PostStatus] = Query(None, alias="status"),
    post_type: Optional[PostType] = Query(None),
    category_id: Optional[int] = Query(None),
    tag_id: Optional[int] = Query(None),
    author_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None, description="Search in title/excerpt"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Public listing with filters + pagination. Use status=published for a public blog feed."""
    return post_controller.list_posts(
        db, status_filter, post_type, category_id, tag_id, author_id, search, page, page_size
    )


@router.get("/slug/{slug}", response_model=PostOut)
def get_post_by_slug(slug: str, track_view: bool = Query(True), db: Session = Depends(get_db)):
    """Public-facing endpoint for rendering a single post page by its slug."""
    return post_controller.get_post_by_slug(db, slug, track_view)


@router.get("/{post_id}", response_model=PostOut)
def get_post(post_id: int, db: Session = Depends(get_db)):
    return post_controller.get_post(db, post_id)


@router.put("/{post_id}", response_model=PostOut)
def update_post(
    post_id: int,
    data: PostUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = post_controller.get_post(db, post_id)
    _ensure_owner_or_editor(post, current_user)
    return post_controller.update_post(db, post_id, data)


@router.delete("/{post_id}")
def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = post_controller.get_post(db, post_id)
    _ensure_owner_or_editor(post, current_user)
    return post_controller.delete_post(db, post_id)


@router.post("/{post_id}/publish", response_model=PostOut)
def publish_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = post_controller.get_post(db, post_id)
    _ensure_owner_or_editor(post, current_user)
    return post_controller.publish_post(db, post_id)


@router.post("/{post_id}/archive", response_model=PostOut)
def archive_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = post_controller.get_post(db, post_id)
    _ensure_owner_or_editor(post, current_user)
    return post_controller.archive_post(db, post_id)
