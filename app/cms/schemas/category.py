# app/cms/schemas/category.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from app.cms.schemas.common import NonNullableUpdateMixin


class CategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = None
    parent_id: Optional[int] = None


class CategoryCreate(CategoryBase):
    slug: Optional[str] = Field(None, description="Auto-generated from name if omitted")


class CategoryUpdate(NonNullableUpdateMixin):
    non_nullable_fields = frozenset({"name", "slug"})

    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None


class CategoryOut(CategoryBase):
    id: int
    slug: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CategoryWithChildren(CategoryOut):
    children: List["CategoryWithChildren"] = []

    model_config = {"from_attributes": True}


CategoryWithChildren.model_rebuild()


class CategoryDeleteOut(BaseModel):
    detail: str
    moved_children: int
    moved_posts: int
    moved_to_category_id: Optional[int]  # required, nullable: null = uncategorised / top level
