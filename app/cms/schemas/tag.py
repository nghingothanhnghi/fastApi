# app/cms/schemas/tag.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime

from app.cms.schemas.common import NonNullableUpdateMixin


class TagBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class TagCreate(TagBase):
    slug: Optional[str] = None


class TagUpdate(NonNullableUpdateMixin):
    """Partial update: omitted fields are untouched; `null` is rejected (422) for both."""
    non_nullable_fields = frozenset({"name", "slug"})

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    slug: Optional[str] = Field(None, max_length=120)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v):
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("name must not be blank")
        return v


class TagOut(TagBase):
    id: int
    slug: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TagDeleteOut(BaseModel):
    detail: str
    posts_affected: int
    merged_into_tag_id: Optional[int]  # required, nullable
    posts_moved: int
