# app/cms/controllers/post_controller.py
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.cms.services.post_service import post_service
from app.cms.models.post import PostStatus, PostType
from app.cms.schemas.post import PostCreate, PostUpdate


class PostController:

    @staticmethod
    def create_post(db: Session, data: PostCreate, author_id: int):
        return post_service.create_post(db, data, author_id)

    @staticmethod
    def get_post(db: Session, post_id: int):
        post = post_service.get_post(db, post_id)
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
        return post

    @staticmethod
    def get_post_by_slug(db: Session, slug: str, track_view: bool = False):
        post = post_service.get_post_by_slug(db, slug)
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
        if track_view:
            post_service.increment_view_count(db, post.id)
        return post

    @staticmethod
    def list_posts(
        db: Session,
        status_filter: Optional[PostStatus],
        post_type: Optional[PostType],
        category_id: Optional[int],
        tag_id: Optional[int],
        author_id: Optional[int],
        search: Optional[str],
        page: int,
        page_size: int,
    ):
        posts, total = post_service.list_posts(
            db,
            status_filter=status_filter,
            post_type=post_type,
            category_id=category_id,
            tag_id=tag_id,
            author_id=author_id,
            search=search,
            page=page,
            page_size=page_size,
        )
        return {"results": posts, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def update_post(db: Session, post_id: int, data: PostUpdate):
        post = post_service.update_post(db, post_id, data)
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
        return post

    @staticmethod
    def delete_post(db: Session, post_id: int):
        success = post_service.delete_post(db, post_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
        return {"detail": "Post deleted successfully"}

    @staticmethod
    def publish_post(db: Session, post_id: int):
        post = post_service.publish_post(db, post_id)
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
        return post

    @staticmethod
    def archive_post(db: Session, post_id: int):
        post = post_service.archive_post(db, post_id)
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
        return post


post_controller = PostController()
