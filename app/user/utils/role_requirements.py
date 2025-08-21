# backend/app/utils/role_requirements.py
# Utility functions for role-based access control in FastAPI

from fastapi import Depends, HTTPException, status
from typing import List, Callable
from app.user.models.user import User
from app.user.utils.token import get_current_user
from app.user.enums.role_enum import RoleEnum

def require_roles(*required_roles: RoleEnum) -> Callable:
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated"
            )

        # Always allow SUPER_ADMIN
        if current_user.has_role(RoleEnum.SUPER_ADMIN):
            return current_user

        if not any(current_user.has_role(role) for role in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {[r.value for r in required_roles]}"
            )
        return current_user
    return dependency


