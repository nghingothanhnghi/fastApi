# app/cms/schemas/tag.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class TagBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class TagCreate(TagBase):
    slug: Optional[str] = None


class TagOut(TagBase):
    id: int
    slug: str
    created_at: datetime

    model_config = {"from_attributes": True}
