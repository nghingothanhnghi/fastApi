# app/transform_data/schemas/template.py
from pydantic import BaseModel
from typing import Dict

class TransformRequest(BaseModel):
    client_id: str
    raw_data: Dict

class TransformResponse(BaseModel):
    transformed_data: Dict