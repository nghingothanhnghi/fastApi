# app/cms/models/category.py
# Supports unlimited nesting via self-referential parent_id (e.g. News > Tech > AI).
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from app.database import Base


class CmsCategory(Base):
    __tablename__ = "cms_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    slug = Column(String(170), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)

    parent_id = Column(Integer, ForeignKey("cms_categories.id", ondelete="SET NULL"), nullable=True)
    parent = relationship("CmsCategory", remote_side=[id], backref="children")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    posts = relationship("CmsPost", back_populates="category")

    def __repr__(self):
        return f"<CmsCategory(id={self.id}, slug={self.slug!r})>"
