# app/cms/services/post_service.py
from typing import List, Optional, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func
from fastapi import HTTPException, status

from app.cms.models.post import CmsPost, PostStatus, PostType
from app.cms.models.category import CmsCategory
from app.cms.models.media import CmsMedia
from app.cms.schemas.post import PostCreate, PostUpdate
from app.cms.services.tag_service import tag_service
from app.cms.utils.slugify import slugify, make_unique_slug, run_with_slug_retry
from app.cms.utils.sanitize import sanitize_html

from app.core.logging_config import get_logger
 
logger = get_logger(__name__)


class PostService:

    # Whitelisted sort keys for list_posts (never interpolate user input into ORDER BY).
    SORT_COLUMNS = {
        "created_at": CmsPost.created_at,
        "published_at": CmsPost.published_at,
        "title": CmsPost.title,
        "view_count": CmsPost.view_count,
    }

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

    @staticmethod
    def _ensure_future_utc(value: datetime) -> datetime:
        """Normalize to aware-UTC (naive input is assumed UTC) and require it to be in the future."""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if value <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="scheduled_at must be in the future",
            )
        return value

    def _validate_refs(
        self,
        db: Session,
        category_id: Optional[int] = None,
        featured_image_id: Optional[int] = None,
        tag_ids: Optional[List[int]] = None,
    ) -> None:
        """Return clear 400s instead of raw FK/IntegrityError 500s."""
        if category_id is not None and not db.query(CmsCategory.id).filter(CmsCategory.id == category_id).first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Category {category_id} not found")
        if featured_image_id is not None and not db.query(CmsMedia.id).filter(CmsMedia.id == featured_image_id).first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Media {featured_image_id} not found")
        if tag_ids:
            found = {t.id for t in tag_service.get_tags_by_ids(db, tag_ids)}
            missing = sorted(set(tag_ids) - found)
            if missing:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Tags not found: {missing}")

    def create_post(self, db: Session, data: PostCreate, author_id: int) -> CmsPost:
        self._validate_refs(db, data.category_id, data.featured_image_id, data.tag_ids)
        base_slug = slugify(data.slug or data.title)
        scheduled_at = data.scheduled_at

        if data.status == PostStatus.scheduled:
            if not scheduled_at:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="scheduled_at is required when status is 'scheduled'",
                )
            scheduled_at = self._ensure_future_utc(scheduled_at)

        def operation() -> int:
            tags = tag_service.get_tags_by_ids(db, data.tag_ids) if data.tag_ids else []
            post = CmsPost(
                title=data.title,
                slug=self._unique_slug(db, base_slug),
                excerpt=data.excerpt,
                content=sanitize_html(data.content),
                post_type=data.post_type,
                status=data.status,
                category_id=data.category_id,
                featured_image_id=data.featured_image_id,
                meta_title=data.meta_title,
                meta_description=data.meta_description,
                is_featured=data.is_featured,
                author_id=author_id,
                tags=tags,
                scheduled_at=scheduled_at,
            )
            if post.status == PostStatus.published:
                post.published_at = datetime.now(timezone.utc)
            db.add(post)
            db.commit()
            return post.id

        post_id = run_with_slug_retry(db, operation)
        return self.get_post(db, post_id)

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
        is_featured: Optional[bool] = None,
        sort: str = "created_at",
        order: str = "desc",
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
        if is_featured is not None:
            query = query.filter(CmsPost.is_featured == is_featured)
        if search:
            like = f"%{search}%"
            query = query.filter(or_(CmsPost.title.ilike(like), CmsPost.excerpt.ilike(like)))

        total = query.with_entities(func.count(CmsPost.id.distinct())).scalar()

        sort_column = self.SORT_COLUMNS.get(sort, CmsPost.created_at)
        descending = order != "asc"
        primary = sort_column.desc() if descending else sort_column.asc()
        if sort == "published_at":
            primary = primary.nullslast()  # drafts (no publish date) never lead a "newest" list
        tiebreak = CmsPost.id.desc() if descending else CmsPost.id.asc()  # stable pagination

        posts = (
            query.order_by(primary, tiebreak)
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
        if update_data.get("content") is not None:
            update_data["content"] = sanitize_html(update_data["content"])

        self._validate_refs(
            db, update_data.get("category_id"), update_data.get("featured_image_id"), tag_ids
        )

        was_published = post.status == PostStatus.published
        new_status = update_data.get("status", post.status)

        # Validate scheduled_at presence/future-ness before applying changes
        if new_status == PostStatus.scheduled:
            incoming_scheduled_at = update_data.get("scheduled_at", post.scheduled_at)
            if not incoming_scheduled_at:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="scheduled_at is required when status is 'scheduled'",
                )
            if "scheduled_at" in update_data or post.status != PostStatus.scheduled:
                update_data["scheduled_at"] = self._ensure_future_utc(incoming_scheduled_at)
        elif update_data.get("scheduled_at") is not None:
            update_data["scheduled_at"] = self._ensure_future_utc(update_data["scheduled_at"])

        def operation() -> Optional[int]:
            # Re-read inside the operation: a retry follows a rollback that expired everything.
            obj = db.query(CmsPost).filter(CmsPost.id == post_id).first()
            if obj is None:
                return None
            values = dict(update_data)
            if values.get("slug"):
                values["slug"] = self._unique_slug(db, slugify(values["slug"]), exclude_id=post_id)
            for field, value in values.items():
                setattr(obj, field, value)

            if tag_ids is not None:
                obj.tags = tag_service.get_tags_by_ids(db, tag_ids)

            # Auto-stamp published_at the first time a post transitions to published
            if obj.status == PostStatus.published and not was_published:
                obj.published_at = datetime.now(timezone.utc)

            # Leaving 'scheduled' (manually or via publish/archive) clears the
            # scheduled_at marker so the background job stops picking it up.
            if new_status != PostStatus.scheduled and "scheduled_at" not in update_data:
                obj.scheduled_at = None

            db.commit()
            return obj.id

        saved_id = run_with_slug_retry(db, operation)
        return self.get_post(db, saved_id) if saved_id else None

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
        post.published_at = datetime.now(timezone.utc)
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

        scheduled_at = self._ensure_future_utc(scheduled_at)

        post.status = PostStatus.scheduled
        post.scheduled_at = scheduled_at
        db.commit()
        db.refresh(post)
        logger.info(f"[CMS] Post {post_id} scheduled for {scheduled_at.isoformat()}")
        return self.get_post(db, post.id)
 
    def get_due_scheduled_posts(self, db: Session) -> List[CmsPost]:
        """Posts whose scheduled_at has passed but are still 'scheduled'."""
        now = datetime.now(timezone.utc)
        return (
            db.query(CmsPost)
            .filter(
                CmsPost.status == PostStatus.scheduled,
                CmsPost.scheduled_at.isnot(None),
                CmsPost.scheduled_at <= now,
            )
            # Several workers may run the job: lock due rows and skip ones another worker holds
            # (ignored on SQLite, honoured on PostgreSQL).
            .with_for_update(skip_locked=True)
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
 
        now = datetime.now(timezone.utc)
        for post in due_posts:
            post.status = PostStatus.published
            post.published_at = now
            post.scheduled_at = None
            logger.info(f"[CMS] Auto-published scheduled post {post.id} ('{post.title}')")
 
        db.commit()
        return len(due_posts)

    def sanitize_all_posts(self, db: Session) -> int:
        """Backfill: re-sanitize stored content. Returns how many posts changed (idempotent)."""
        changed = 0
        for post in db.query(CmsPost).yield_per(100):
            clean = sanitize_html(post.content)
            if clean != post.content:
                post.content = clean
                changed += 1
        db.commit()
        return changed


post_service = PostService()
