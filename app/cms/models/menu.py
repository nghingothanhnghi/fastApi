# app/cms/models/menu.py
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Enum, func
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class MenuItemTargetType(str, enum.Enum):
    custom = "custom"      # arbitrary URL
    category = "category"  # links to a CmsCategory
    post = "post"          # links to a CmsPost


class CmsMenu(Base):
    __tablename__ = "cms_menus"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    slug = Column(String(170), unique=True, index=True, nullable=False)
    # Optional fixed placement key, e.g. "header", "footer" — lets the
    # frontend fetch "the header menu" without hardcoding an id/slug.
    location = Column(String(50), unique=True, index=True, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    items = relationship(
        "CmsMenuItem",
        back_populates="menu",
        cascade="all, delete-orphan",
        order_by="CmsMenuItem.order",
    )

    def __repr__(self):
        return f"<CmsMenu(id={self.id}, slug={self.slug!r})>"


class CmsMenuItem(Base):
    __tablename__ = "cms_menu_items"

    id = Column(Integer, primary_key=True, index=True)
    menu_id = Column(Integer, ForeignKey("cms_menus.id", ondelete="CASCADE"), nullable=False)
    menu = relationship("CmsMenu", back_populates="items")

    parent_id = Column(Integer, ForeignKey("cms_menu_items.id", ondelete="CASCADE"), nullable=True)
    parent = relationship("CmsMenuItem", remote_side=[id], backref="children")

    label = Column(String(150), nullable=False)

    target_type = Column(Enum(MenuItemTargetType), default=MenuItemTargetType.custom, nullable=False)
    # For target_type == custom: the literal URL.
    # For target_type in (category, post): target_id is used instead and
    # the url is resolved at read time (see menu_service.resolve_item_url).
    url = Column(String(500), nullable=True)
    target_id = Column(Integer, nullable=True)

    order = Column(Integer, default=0, nullable=False)
    open_in_new_tab = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<CmsMenuItem(id={self.id}, label={self.label!r})>"