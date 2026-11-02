# app/cms/routes/post_router.py
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.user.utils.token import get_current_user, get_current_user_optional
from app.user.enums.role_enum import RoleEnum
from app.user.models.user import User
from app.cms.models.post import PostStatus, PostType
from app.cms.schemas.post import PostCreate, PostUpdate, PostOut, PaginatedPosts, PostScheduleRequest
from app.cms.controllers.post_controller import post_controller
from app.cms.services.post_service import post_service

router = APIRouter(prefix="/cms/posts", tags=["CMS - Posts"])


def _is_editor(user: Optional[User]) -> bool:
    return bool(user) and (
        user.has_role(RoleEnum.SUPER_ADMIN)
        or user.has_role(RoleEnum.ADMIN)
        or user.has_role(RoleEnum.MODERATOR)
    )


def _ensure_visible(post, user: Optional[User]) -> None:
    """Unpublished posts are only visible to their author and editors (404 for everyone else)."""
    if post.status == PostStatus.published:
        return
    if _is_editor(user) or (user is not None and post.author_id == user.id):
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")


def _ensure_owner_or_editor(post, current_user: User) -> None:
    """Author of the post, or ADMIN/SUPER_ADMIN/MODERATOR, may modify it."""
    if post.author_id != current_user.id and not _is_editor(current_user):
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
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Listing with filters + pagination.
    Anonymous users (and non-editors) only ever see `published` posts; asking for another
    status is a 403. Editors see everything; authors may list their own posts (author_id=<self>).
    """
    can_see_all = _is_editor(current_user) or (
        current_user is not None and author_id is not None and author_id == current_user.id
    )
    if not can_see_all:
        if status_filter not in (None, PostStatus.published):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only published posts are available",
            )
        status_filter = PostStatus.published
    return post_controller.list_posts(
        db, status_filter, post_type, category_id, tag_id, author_id, search, page, page_size
    )


@router.get("/slug/{slug}", response_model=PostOut)
def get_post_by_slug(
    slug: str,
    track_view: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Public-facing endpoint for rendering a single post page by its slug (published only for the public)."""
    post = post_controller.get_post_by_slug(db, slug, track_view=False)
    _ensure_visible(post, current_user)
    if track_view and post.status == PostStatus.published:
        post_service.increment_view_count(db, post.id)
    return post


@router.get("/{post_id}", response_model=PostOut)
def get_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    post = post_controller.get_post(db, post_id)
    _ensure_visible(post, current_user)
    return post


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

@router.post("/{post_id}/schedule", response_model=PostOut)
def schedule_post(
    post_id: int,
    data: PostScheduleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Set a post to auto-publish at a future datetime.
    Status flips to 'scheduled' now, then a background job (polling every
    minute) flips it to 'published' once `scheduled_at` passes.
    """
    post = post_controller.get_post(db, post_id)
    _ensure_owner_or_editor(post, current_user)
    return post_controller.schedule_post(db, post_id, data.scheduled_at)