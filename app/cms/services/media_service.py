# app/cms/services/media_service.py
# Handles physical file storage + the CmsMedia DB record in one place.
# Same pattern as app/product/services/image_service.py, generalized for the
# CMS media library (multiple file types, size limits, alt text, delete-from-disk).
import os
import shutil
from uuid import uuid4
from typing import Optional, List
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session

from app.cms.models.media import CmsMedia
from app.cms.config import CMS_MEDIA_DIR, CMS_MEDIA_URL, ALLOWED_MEDIA_EXTENSIONS, MAX_MEDIA_SIZE_MB
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class MediaService:

    def _validate_file(self, file: UploadFile) -> str:
        if not file or not file.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file provided")

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_MEDIA_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_MEDIA_EXTENSIONS))}",
            )
        return ext

    def upload_media(
        self,
        db: Session,
        file: UploadFile,
        uploaded_by_id: Optional[int] = None,
        alt_text: Optional[str] = None,
    ) -> CmsMedia:
        ext = self._validate_file(file)

        os.makedirs(CMS_MEDIA_DIR, exist_ok=True)
        filename = f"{uuid4().hex}{ext}"
        file_path = os.path.join(CMS_MEDIA_DIR, filename)

        # Measure size without loading the whole file into memory
        file.file.seek(0, os.SEEK_END)
        size_bytes = file.file.tell()
        file.file.seek(0)

        if size_bytes > MAX_MEDIA_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File exceeds max size of {MAX_MEDIA_SIZE_MB}MB",
            )

        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception:
            logger.exception("Failed to save CMS media file", extra={"path": file_path})
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to save file")

        media = CmsMedia(
            filename=file.filename,
            url=f"{CMS_MEDIA_URL.rstrip('/')}/{filename}",
            mime_type=file.content_type,
            file_size=size_bytes,
            alt_text=alt_text,
            uploaded_by_id=uploaded_by_id,
        )
        db.add(media)
        db.commit()
        db.refresh(media)
        logger.info("CMS media uploaded", extra={"media_id": media.id, "path": file_path})
        return media

    def get_media(self, db: Session, media_id: int) -> Optional[CmsMedia]:
        return db.query(CmsMedia).filter(CmsMedia.id == media_id).first()

    def get_all_media(self, db: Session, skip: int = 0, limit: int = 50) -> List[CmsMedia]:
        return (
            db.query(CmsMedia)
            .order_by(CmsMedia.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def update_media(self, db: Session, media_id: int, alt_text: Optional[str]) -> Optional[CmsMedia]:
        media = self.get_media(db, media_id)
        if not media:
            return None
        media.alt_text = alt_text
        db.commit()
        db.refresh(media)
        return media

    def delete_media(self, db: Session, media_id: int) -> bool:
        media = self.get_media(db, media_id)
        if not media:
            return False

        # Best-effort removal from disk; DB row is the source of truth either way
        try:
            filename = media.url.rstrip("/").split("/")[-1]
            file_path = os.path.join(CMS_MEDIA_DIR, filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            logger.warning("Could not remove media file from disk", extra={"media_id": media_id})

        db.delete(media)
        db.commit()
        return True


media_service = MediaService()
