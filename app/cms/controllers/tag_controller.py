# app/cms/controllers/tag_controller.py
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.cms.services.tag_service import tag_service
from app.cms.schemas.tag import TagCreate


class TagController:

    @staticmethod
    def create_tag(db: Session, data: TagCreate):
        return tag_service.create_tag(db, data)

    @staticmethod
    def get_all_tags(db: Session):
        return tag_service.get_all_tags(db)

    @staticmethod
    def delete_tag(db: Session, tag_id: int):
        success = tag_service.delete_tag(db, tag_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
        return {"detail": "Tag deleted successfully"}


tag_controller = TagController()
