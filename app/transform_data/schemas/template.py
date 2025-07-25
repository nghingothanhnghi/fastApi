# app/transform_data/schemas/template.py
from pydantic import BaseModel, Field
from typing import Dict, Optional
from datetime import datetime

# === Transformation ===
class TransformRequest(BaseModel):
    client_id: str
    raw_data: Dict

class TransformResponse(BaseModel):
    transformed_data: Dict

# === Template CRUD ===
class TemplateCreate(BaseModel):
    client_id: str
    mapping: Dict[str, str]  # target_field -> source_field mapping

class TemplateUpdate(BaseModel):
    mapping: Dict[str, str]

class TemplateOut(BaseModel):
    id: int
    client_id: str
    mapping: Dict[str, str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True

# === AI Mapping Suggestion ===

class SuggestMappingRequest(BaseModel):
    client_id: str = Field(..., example="client_123")
    raw_data: Dict = Field(..., example={"source_name": "John", "source_age": 30})

class SuggestMappingResponse(BaseModel):
    client_id: str
    suggested_mapping: Dict[str, str]