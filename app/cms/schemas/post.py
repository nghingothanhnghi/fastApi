# app/cms/schemas/post.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from app.cms.models.post import PostStatus, PostType
from app.cms.schemas.tag import TagOut
from app.cms.schemas.category import CategoryOut
from app.cms.schemas.media import MediaOut


class PostBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    excerpt: Optional[str] = Field(None, max_length=500)
    content: str = ""
    post_type: PostType = PostType.post
    status: PostStatus = PostStatus.draft
    category_id: Optional[int] = None
    featured_image_id: Optional[int] = Field(
        None, description="id returned by POST /cms/media/upload"
    )
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    is_featured: bool = False


class PostCreate(PostBase):
    slug: Optional[str] = Field(None, description="Auto-generated from title if omitted")
    tag_ids: List[int] = []


class PostUpdate(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    excerpt: Optional[str] = None
    content: Optional[str] = None
    post_type: Optional[PostType] = None
    status: Optional[PostStatus] = None
    category_id: Optional[int] = None
    featured_image_id: Optional[int] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    is_featured: Optional[bool] = None
    tag_ids: Optional[List[int]] = None


class AuthorOut(BaseModel):
    id: int
    username: str

    model_config = {"from_attributes": True}


class PostOut(PostBase):
    id: int
    slug: str
    author: Optional[AuthorOut] = None
    category: Optional[CategoryOut] = None
    featured_image: Optional[MediaOut] = None
    tags: List[TagOut] = []
    view_count: int
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PostListItem(BaseModel):
    """Lightweight schema for list/grid views (omits full `content` body)."""
    id: int
    title: str
    slug: str
    excerpt: Optional[str] = None
    status: PostStatus
    post_type: PostType
    author: Optional[AuthorOut] = None
    category: Optional[CategoryOut] = None
    featured_image: Optional[MediaOut] = None
    is_featured: bool
    view_count: int
    published_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedPosts(BaseModel):
    results: List[PostListItem]
    total: int
    page: int
    page_size: int
