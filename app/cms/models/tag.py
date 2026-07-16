# app/cms/models/tag.py
from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import relationship
from app.database import Base


class CmsTag(Base):
    __tablename__ = "cms_tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    slug = Column(String(120), unique=True, index=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    posts = relationship("CmsPost", secondary="cms_post_tags", back_populates="tags")

    def __repr__(self):
        return f"<CmsTag(id={self.id}, slug={self.slug!r})>"
