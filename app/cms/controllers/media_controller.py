# app/cms/controllers/media_controller.py
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from typing import Optional
from app.cms.services.media_service import media_service


class MediaController:

    @staticmethod
    def upload_media(db: Session, file: UploadFile, uploaded_by_id: Optional[int], alt_text: Optional[str] = None):
        return media_service.upload_media(db, file, uploaded_by_id, alt_text)

    @staticmethod
    def get_media(db: Session, media_id: int):
        media = media_service.get_media(db, media_id)
        if not media:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
        return media

    @staticmethod
    def get_all_media(db: Session, skip: int = 0, limit: int = 50):
        return media_service.get_all_media(db, skip, limit)

    @staticmethod
    def update_media(db: Session, media_id: int, alt_text: Optional[str]):
        media = media_service.update_media(db, media_id, alt_text)
        if not media:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
        return media

    @staticmethod
    def delete_media(db: Session, media_id: int):
        success = media_service.delete_media(db, media_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
        return {"detail": "Media deleted successfully"}


media_controller = MediaController()
