# app/cms/schemas/media.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class MediaOut(BaseModel):
    id: int
    filename: str
    url: str
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    alt_text: Optional[str] = None
    uploaded_by_id: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MediaUpdate(BaseModel):
    alt_text: Optional[str] = None
