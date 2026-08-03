# app/cms/services/post_service.py
from typing import List, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func
from fastapi import HTTPException, status

from app.cms.models.post import CmsPost, PostStatus, PostType
from app.cms.schemas.post import PostCreate, PostUpdate
from app.cms.services.tag_service import tag_service
from app.cms.utils.slugify import slugify, make_unique_slug

from app.core.logging_config import get_logger
 
logger = get_logger(__name__)


class PostService:

    def _base_query(self, db: Session):
        # Eager-load everything the PostOut/PostListItem schemas need, in one query.
        return db.query(CmsPost).options(
            joinedload(CmsPost.author),
            joinedload(CmsPost.category),
            joinedload(CmsPost.featured_image),
            joinedload(CmsPost.tags),
        )

    def _unique_slug(self, db: Session, base: str, exclude_id: Optional[int] = None) -> str:
        def exists(slug: str) -> bool:
            q = db.query(CmsPost).filter(CmsPost.slug == slug)
            if exclude_id:
                q = q.filter(CmsPost.id != exclude_id)
            return db.query(q.exists()).scalar()
        return make_unique_slug(base, exists)

    def create_post(self, db: Session, data: PostCreate, author_id: int) -> CmsPost:
        base_slug = slugify(data.slug or data.title)
        tags = tag_service.get_tags_by_ids(db, data.tag_ids) if data.tag_ids else []

        post = CmsPost(
            title=data.title,
            slug=self._unique_slug(db, base_slug),
            excerpt=data.excerpt,
            content=data.content,
            post_type=data.post_type,
            status=data.status,
            category_id=data.category_id,
            featured_image_id=data.featured_image_id,
            meta_title=data.meta_title,
            meta_description=data.meta_description,
            is_featured=data.is_featured,
            author_id=author_id,
            tags=tags,
        )
        if post.status == PostStatus.published:
            post.published_at = datetime.utcnow()

        db.add(post)
        db.commit()
        db.refresh(post)
        return self.get_post(db, post.id)

    def get_post(self, db: Session, post_id: int) -> Optional[CmsPost]:
        return self._base_query(db).filter(CmsPost.id == post_id).first()

    def get_post_by_slug(self, db: Session, slug: str) -> Optional[CmsPost]:
        return self._base_query(db).filter(CmsPost.slug == slug).first()

    def list_posts(
        self,
        db: Session,
        status_filter: Optional[PostStatus] = None,
        post_type: Optional[PostType] = None,
        category_id: Optional[int] = None,
        tag_id: Optional[int] = None,
        author_id: Optional[int] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[CmsPost], int]:
        query = self._base_query(db)

        if status_filter:
            query = query.filter(CmsPost.status == status_filter)
        if post_type:
            query = query.filter(CmsPost.post_type == post_type)
        if category_id:
            query = query.filter(CmsPost.category_id == category_id)
        if author_id:
            query = query.filter(CmsPost.author_id == author_id)
        if tag_id:
            query = query.filter(CmsPost.tags.any(id=tag_id))
        if search:
            like = f"%{search}%"
            query = query.filter(or_(CmsPost.title.ilike(like), CmsPost.excerpt.ilike(like)))

        total = query.with_entities(func.count(CmsPost.id.distinct())).scalar()

        posts = (
            query.order_by(CmsPost.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return posts, total

    def update_post(self, db: Session, post_id: int, data: PostUpdate) -> Optional[CmsPost]:
        post = db.query(CmsPost).filter(CmsPost.id == post_id).first()
        if not post:
            return None

        update_data = data.model_dump(exclude_unset=True)
        tag_ids = update_data.pop("tag_ids", None)

        if update_data.get("slug"):
            update_data["slug"] = self._unique_slug(db, slugify(update_data["slug"]), exclude_id=post_id)

        was_published = post.status == PostStatus.published
        new_status = update_data.get("status", post.status)

        for field, value in update_data.items():
            setattr(post, field, value)

        if tag_ids is not None:
            post.tags = tag_service.get_tags_by_ids(db, tag_ids)

        # Auto-stamp published_at the first time a post transitions to published
        if post.status == PostStatus.published and not was_published:
            post.published_at = datetime.utcnow()

        # Leaving 'scheduled' (manually or via publish/archive) clears the
        # scheduled_at marker so the background job stops picking it up.
        if new_status != PostStatus.scheduled and "scheduled_at" not in update_data:
            post.scheduled_at = None            

        db.commit()
        db.refresh(post)
        return self.get_post(db, post.id)

    def delete_post(self, db: Session, post_id: int) -> bool:
        post = db.query(CmsPost).filter(CmsPost.id == post_id).first()
        if not post:
            return False
        db.delete(post)
        db.commit()
        return True

    def increment_view_count(self, db: Session, post_id: int) -> None:
        db.query(CmsPost).filter(CmsPost.id == post_id).update(
            {CmsPost.view_count: CmsPost.view_count + 1}
        )
        db.commit()

    def publish_post(self, db: Session, post_id: int) -> Optional[CmsPost]:
        post = db.query(CmsPost).filter(CmsPost.id == post_id).first()
        if not post:
            return None
        post.status = PostStatus.published
        post.published_at = datetime.utcnow()
        post.scheduled_at = None
        db.commit()
        db.refresh(post)
        return self.get_post(db, post.id)

    def archive_post(self, db: Session, post_id: int) -> Optional[CmsPost]:
        post = db.query(CmsPost).filter(CmsPost.id == post_id).first()
        if not post:
            return None
        post.status = PostStatus.archived
        post.scheduled_at = None
        db.commit()
        db.refresh(post)
        return self.get_post(db, post.id)

    # ──────────────────────────────────────────────────────────────────────
    # ⏰ Scheduled publishing
    # ──────────────────────────────────────────────────────────────────────
 
    def schedule_post(self, db: Session, post_id: int, scheduled_at: datetime) -> Optional[CmsPost]:
        """Mark a post as 'scheduled' to auto-publish at `scheduled_at`."""
        post = db.query(CmsPost).filter(CmsPost.id == post_id).first()
        if not post:
            return None
 
        if scheduled_at <= datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="scheduled_at must be in the future",
            )
 
        post.status = PostStatus.scheduled
        post.scheduled_at = scheduled_at
        db.commit()
        db.refresh(post)
        logger.info(f"[CMS] Post {post_id} scheduled for {scheduled_at.isoformat()}")
        return self.get_post(db, post.id)
 
    def get_due_scheduled_posts(self, db: Session) -> List[CmsPost]:
        """Posts whose scheduled_at has passed but are still 'scheduled'."""
        now = datetime.utcnow()
        return (
            db.query(CmsPost)
            .filter(
                CmsPost.status == PostStatus.scheduled,
                CmsPost.scheduled_at.isnot(None),
                CmsPost.scheduled_at <= now,
            )
            .all()
        )
 
    def publish_due_scheduled_posts(self, db: Session) -> int:
        """
        Flip every due 'scheduled' post to 'published'.
        Intended to be called periodically by a background job. Returns the
        number of posts published.
        """
        due_posts = self.get_due_scheduled_posts(db)
        if not due_posts:
            return 0
 
        now = datetime.utcnow()
        for post in due_posts:
            post.status = PostStatus.published
            post.published_at = now
            post.scheduled_at = None
            logger.info(f"[CMS] Auto-published scheduled post {post.id} ('{post.title}')")
 
        db.commit()
        return len(due_posts)


post_service = PostService()
