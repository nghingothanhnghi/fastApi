# app/cms/services/tag_service.py
from typing import List, Optional
from sqlalchemy.orm import Session
from app.cms.models.tag import CmsTag
from app.cms.schemas.tag import TagCreate
from app.cms.utils.slugify import slugify, make_unique_slug


class TagService:

    def _unique_slug(self, db: Session, base: str) -> str:
        def exists(slug: str) -> bool:
            return db.query(db.query(CmsTag).filter(CmsTag.slug == slug).exists()).scalar()
        return make_unique_slug(base, exists)

    def create_tag(self, db: Session, data: TagCreate) -> CmsTag:
        base_slug = slugify(data.slug or data.name)
        tag = CmsTag(name=data.name.strip(), slug=self._unique_slug(db, base_slug))
        db.add(tag)
        db.commit()
        db.refresh(tag)
        return tag

    def get_or_create_tag(self, db: Session, name: str) -> CmsTag:
        """Handy for free-text tag input (e.g. a CMS editor tag box)."""
        existing = db.query(CmsTag).filter(CmsTag.name.ilike(name.strip())).first()
        if existing:
            return existing
        return self.create_tag(db, TagCreate(name=name.strip()))

    def get_tag(self, db: Session, tag_id: int) -> Optional[CmsTag]:
        return db.query(CmsTag).filter(CmsTag.id == tag_id).first()

    def get_tags_by_ids(self, db: Session, tag_ids: List[int]) -> List[CmsTag]:
        if not tag_ids:
            return []
        return db.query(CmsTag).filter(CmsTag.id.in_(tag_ids)).all()

    def get_all_tags(self, db: Session) -> List[CmsTag]:
        return db.query(CmsTag).order_by(CmsTag.name.asc()).all()

    def delete_tag(self, db: Session, tag_id: int) -> bool:
        tag = self.get_tag(db, tag_id)
        if not tag:
            return False
        db.delete(tag)
        db.commit()
        return True


tag_service = TagService()
