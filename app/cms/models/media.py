# app/cms/models/media.py
# Media library: every uploaded file (image, pdf, video) gets one row here.
# Posts reference media by id (featured_image_id) instead of storing raw URLs,
# so re-use, alt-text/SEO editing, and cleanup are all centralized.
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base


class CmsMedia(Base):
    __tablename__ = "cms_media"

    id = Column(Integer, primary_key=True, index=True)

    filename = Column(String(255), nullable=False)   # original filename
    url = Column(String(500), nullable=False)         # public, frontend-safe URL
    mime_type = Column(String(100), nullable=True)
    file_size = Column(BigInteger, nullable=True)      # bytes
    alt_text = Column(String(255), nullable=True)

    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    uploaded_by = relationship("User")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<CmsMedia(id={self.id}, filename={self.filename!r})>"
