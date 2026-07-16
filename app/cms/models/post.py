# app/cms/models/post.py
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Enum, Table, Boolean, func
)
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class PostStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    scheduled = "scheduled"
    archived = "archived"


class PostType(str, enum.Enum):
    post = "post"   # blog/news article
    page = "page"   # static page (About, Contact, ...)


# Many-to-many association table: posts <-> tags
cms_post_tags = Table(
    "cms_post_tags",
    Base.metadata,
    Column("post_id", Integer, ForeignKey("cms_posts.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("cms_tags.id", ondelete="CASCADE"), primary_key=True),
)


class CmsPost(Base):
    __tablename__ = "cms_posts"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String(255), nullable=False)
    slug = Column(String(280), unique=True, index=True, nullable=False)
    excerpt = Column(String(500), nullable=True)
    content = Column(Text, nullable=False, default="")

    post_type = Column(Enum(PostType), default=PostType.post, nullable=False)
    status = Column(Enum(PostStatus), default=PostStatus.draft, nullable=False, index=True)

    # ✅ Reuses existing users table/auth — no duplicate author model
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    author = relationship("User")

    category_id = Column(Integer, ForeignKey("cms_categories.id", ondelete="SET NULL"), nullable=True)
    category = relationship("CmsCategory", back_populates="posts")

    # ✅ Reuses the media library instead of storing a raw image URL
    featured_image_id = Column(Integer, ForeignKey("cms_media.id", ondelete="SET NULL"), nullable=True)
    featured_image = relationship("CmsMedia")

    tags = relationship("CmsTag", secondary=cms_post_tags, back_populates="posts")

    # SEO
    meta_title = Column(String(255), nullable=True)
    meta_description = Column(String(500), nullable=True)

    is_featured = Column(Boolean, default=False)
    view_count = Column(Integer, default=0, nullable=False)

    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<CmsPost(id={self.id}, title={self.title!r}, status={self.status})>"
