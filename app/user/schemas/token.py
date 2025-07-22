# app/user/schemas/token.py
# This module defines the schemas for token management operations.
from pydantic import BaseModel

class Token(BaseModel):
    access_token: str
    token_type: str
