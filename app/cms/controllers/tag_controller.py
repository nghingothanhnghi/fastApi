# app/cms/controllers/tag_controller.py
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.cms.services.tag_service import tag_service
from app.cms.schemas.tag import TagCreate, TagUpdate


class TagController:

    @staticmethod
    def get_tag_by_slug(db: Session, slug: str):
        tag = tag_service.get_tag_by_slug(db, slug)
        if not tag:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
        return tag

    @staticmethod
    def create_tag(db: Session, data: TagCreate):
        return tag_service.create_tag(db, data)

    @staticmethod
    def update_tag(db: Session, tag_id: int, data: TagUpdate):
        tag = tag_service.update_tag(db, tag_id, data)
        if not tag:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
        return tag

    @staticmethod
    def get_all_tags(db: Session):
        return tag_service.get_all_tags(db)

    @staticmethod
    def delete_tag(db: Session, tag_id: int, force: bool = False, merge_into: Optional[int] = None):
        result = tag_service.delete_tag(db, tag_id, force, merge_into)
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
        return result


tag_controller = TagController()
