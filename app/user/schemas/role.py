# app/user/schemas/role.py
# This module defines the schemas for role management operations.
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
import json

class RoleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="Unique role name")
    display_name: str = Field(..., min_length=1, max_length=100, description="Human-readable role name")
    description: Optional[str] = Field(None, description="Role description")
    is_active: bool = Field(True, description="Whether the role is active")
    permissions: Optional[List[str]] = Field(None, description="List of permissions")

    @field_validator("permissions", mode="before")
    @classmethod
    def parse_permissions(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return []
        return v

    model_config = {
        "from_attributes": True
    }

class RoleCreate(RoleBase):
    pass

class RoleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    permissions: Optional[List[str]] = None

    model_config = {
        "from_attributes": True
    }

class RoleOut(RoleBase):
    id: int
    is_system_role: bool
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {
        "from_attributes": True
    }

class RoleWithUsers(RoleOut):
    user_count: int = Field(..., description="Number of users with this role")

    model_config = {
        "from_attributes": True
    }

# User Role Assignment Schemas
class UserRoleBase(BaseModel):
    user_id: int
    role_id: int

    model_config = {
        "from_attributes": True
    }

class UserRoleCreate(UserRoleBase):
    pass

class UserRoleOut(UserRoleBase):
    id: int
    assigned_at: datetime
    assigned_by: Optional[int] = None

    model_config = {
        "from_attributes": True
    }

class UserRoleWithDetails(UserRoleOut):
    role: RoleOut
    assigned_by_username: Optional[str] = None

    model_config = {
        "from_attributes": True
    }

# Bulk operations
class BulkRoleAssignment(BaseModel):
    user_ids: List[int] = Field(..., min_items=1, description="List of user IDs")
    role_ids: List[int] = Field(..., min_items=1, description="List of role IDs to assign")

class BulkRoleRemoval(BaseModel):
    user_ids: List[int] = Field(..., min_items=1, description="List of user IDs")
    role_ids: List[int] = Field(..., min_items=1, description="List of role IDs to remove")