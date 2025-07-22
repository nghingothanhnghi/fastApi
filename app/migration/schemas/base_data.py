# app/migration/schemas/base_data.py
from pydantic import BaseModel
from typing import Any, Dict

class RawDataIn(BaseModel):
    client_id: str
    payload: Dict[str, Any]

class RawDataOut(RawDataIn):
    id: int