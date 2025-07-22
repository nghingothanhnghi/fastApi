# app/user/schemas/user.py
# This module defines the schemas for user management operations.
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

# Lightweight version for nesting references
class UserOutLite(BaseModel):
    id: int
    username: str
    email: EmailStr

    model_config = {
        "from_attributes": True
    }

class UserBase(BaseModel):
    username: str
    email: EmailStr
    phone_number: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    image_url: Optional[str] = None

    model_config = {
        "from_attributes": True
    }

class UserCreate(UserBase):
    password: str  # ✅ NEW
    client_id: Optional[str] = None  # ✅ Only if public or external creation is allowed

class UserUpdate(BaseModel):
    username: str | None = None
    password: str | None = None
    email: Optional[EmailStr]
    phone_number: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]

    model_config = {
        "from_attributes": True
    }

class UserOut(UserBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime]
    created_by_id: Optional[int] = None  # ✅ Add this to expose who created the user
    created_by: Optional[UserOutLite] = None  # ✅ full created_by user

    model_config = {
        "from_attributes": True
    }

class UserWithRoles(UserOut):
    roles: List['RoleOut'] = []

    model_config = {
        "from_attributes": True
    }

# Forward reference resolution
from .role import RoleOut
UserWithRoles.model_rebuild()
