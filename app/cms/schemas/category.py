# app/cms/schemas/category.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class CategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = None
    parent_id: Optional[int] = None


class CategoryCreate(CategoryBase):
    slug: Optional[str] = Field(None, description="Auto-generated from name if omitted")


class CategoryUpdate(BaseModel):
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
