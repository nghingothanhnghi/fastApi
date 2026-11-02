# app/cms/services/tag_service.py
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.cms.models.tag import CmsTag
from app.cms.models.post import cms_post_tags
from app.cms.schemas.tag import TagCreate
from app.cms.utils.slugify import slugify, make_unique_slug, run_with_slug_retry


class TagService:

    def _unique_slug(self, db: Session, base: str) -> str:
        def exists(slug: str) -> bool:
            return db.query(db.query(CmsTag).filter(CmsTag.slug == slug).exists()).scalar()
        return make_unique_slug(base, exists)

    def create_tag(self, db: Session, data: TagCreate) -> CmsTag:
        if db.query(CmsTag.id).filter(CmsTag.name.ilike(data.name.strip())).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Tag '{data.name.strip()}' already exists")
        base_slug = slugify(data.slug or data.name)
        name = data.name.strip()

        def operation() -> int:
            tag = CmsTag(name=name, slug=self._unique_slug(db, base_slug))
            db.add(tag)
            db.commit()
            return tag.id

        return self.get_tag(db, run_with_slug_retry(db, operation))

    def get_or_create_tag(self, db: Session, name: str) -> CmsTag:
        """Handy for free-text tag input (e.g. a CMS editor tag box)."""
        existing = db.query(CmsTag).filter(CmsTag.name.ilike(name.strip())).first()
        if existing:
            return existing
        try:
            return self.create_tag(db, TagCreate(name=name.strip()))
        except HTTPException as exc:
            # Lost a race with another request creating the same tag: use theirs.
            if exc.status_code != status.HTTP_409_CONFLICT:
                raise
            return db.query(CmsTag).filter(CmsTag.name.ilike(name.strip())).first()

    def get_tag(self, db: Session, tag_id: int) -> Optional[CmsTag]:
        return db.query(CmsTag).filter(CmsTag.id == tag_id).first()

    def get_tags_by_ids(self, db: Session, tag_ids: List[int]) -> List[CmsTag]:
        if not tag_ids:
            return []
        return db.query(CmsTag).filter(CmsTag.id.in_(tag_ids)).all()

    def get_all_tags(self, db: Session) -> List[CmsTag]:
        return db.query(CmsTag).order_by(CmsTag.name.asc()).all()

    def delete_tag(
        self, db: Session, tag_id: int, force: bool = False, merge_into: Optional[int] = None
    ) -> Optional[dict]:
        """
        Delete a tag without silently stripping it from posts.

        - Unused tag: deleted.
        - Used tag: 409 unless `force=True` (detach from posts, then delete) or
          `merge_into=<tag id>` (posts get that tag instead, then delete).

        Returns a summary dict, or None when the tag does not exist.
        """
        tag = self.get_tag(db, tag_id)
        if not tag:
            return None

        post_ids = [
            row[0] for row in db.execute(select(cms_post_tags.c.post_id).where(cms_post_tags.c.tag_id == tag_id))
        ]
        merged = 0

        if merge_into is not None:
            if merge_into == tag_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="merge_into cannot be the tag being deleted")
            if not self.get_tag(db, merge_into):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Tag {merge_into} not found")
            already = {
                row[0]
                for row in db.execute(select(cms_post_tags.c.post_id).where(cms_post_tags.c.tag_id == merge_into))
            }
            rows = [{"post_id": pid, "tag_id": merge_into} for pid in post_ids if pid not in already]
            if rows:
                db.execute(cms_post_tags.insert(), rows)
            merged = len(rows)
        elif post_ids and not force:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Tag is used by {len(post_ids)} post(s); pass force=true to detach it or merge_into=<tag id>",
            )

        db.delete(tag)  # ORM also removes this tag's rows from cms_post_tags
        db.commit()
        return {
            "detail": "Tag deleted successfully",
            "posts_affected": len(post_ids),
            "merged_into_tag_id": merge_into,
            "posts_moved": merged,
        }


tag_service = TagService()
