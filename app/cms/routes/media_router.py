# app/cms/routes/media_router.py
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.user.utils.token import get_current_user
from app.user.models.user import User
from app.cms.schemas.media import MediaOut
from app.cms.controllers.media_controller import media_controller

router = APIRouter(prefix="/cms/media", tags=["CMS - Media"])


@router.post("/upload", response_model=MediaOut, status_code=201)
def upload_media(
    file: UploadFile = File(...),
    alt_text: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a file to the CMS media library.
    Returns the media record (with `id` + `url`) — pass its `id` as `featured_image_id`
    when creating/updating a post, or embed `url` directly in the post's `content`.
    """
    return media_controller.upload_media(db, file, current_user.id, alt_text)


@router.get("", response_model=List[MediaOut])
def list_media(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Browse the media library (e.g. to power an image picker in an editor UI)."""
    return media_controller.get_all_media(db, skip, limit)


@router.get("/{media_id}", response_model=MediaOut)
def get_media(media_id: int, db: Session = Depends(get_db)):
    return media_controller.get_media(db, media_id)


@router.patch("/{media_id}", response_model=MediaOut)
def update_media(
    media_id: int,
    alt_text: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return media_controller.update_media(db, media_id, alt_text)


@router.delete("/{media_id}")
def delete_media(
    media_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return media_controller.delete_media(db, media_id)
