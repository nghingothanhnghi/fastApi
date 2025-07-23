# app/transform_data/schemas/template.py
from pydantic import BaseModel
from typing import Dict

class TransformRequest(BaseModel):
    client_id: str
    raw_data: Dict

class TransformResponse(BaseModel):
    transformed_data: Dict

class TemplateCreate(BaseModel):
    client_id: str
    mapping: Dict[str, str]  # target_field -> source_field mapping

class TemplateUpdate(BaseModel):
    mapping: Dict[str, str]

class TemplateOut(BaseModel):
    id: int
    client_id: str
    mapping: Dict[str, str]
    
    class Config:
        from_attributes = True