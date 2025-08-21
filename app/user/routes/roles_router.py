# app/api/endpoints/roles.py
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from app.database import get_db
from app.user.utils.token import get_current_user
from app.user.utils.role_requirements import require_roles
from app.user.models.user import User
from app.user.services.role_service import RoleService
from app.user.schemas.role import (
    RoleCreate, RoleUpdate, RoleOut, RoleWithUsers,
    UserRoleCreate, UserRoleOut, UserRoleWithDetails,
    BulkRoleAssignment, BulkRoleRemoval
)
from app.user.schemas.user import UserWithRoles
from app.user.enums.role_enum import RoleEnum


router = APIRouter(prefix="/roles", tags=["Roles"])
logger = logging.getLogger(__name__)

def get_role_service(db: Session = Depends(get_db)) -> RoleService:
    return RoleService(db)

# Role CRUD Operations
@router.post("/", response_model=RoleOut)
def create_role(
    role_data: RoleCreate,
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN))
):
    """Create a new role (Admin only)"""
    try:
        role = role_service.create_role(role_data, current_user.id)
        logger.info(f"Role created: {role.name} by user {current_user.id}")
        return role
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create role: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create role"
        )

@router.get("", response_model=List[RoleOut])
def get_all_roles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    active_only: bool = Query(True),
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(get_current_user)
):
    """Get all roles with pagination"""
    roles = role_service.get_all_roles(skip=skip, limit=limit, active_only=active_only)
    logger.info(f"Retrieved {len(roles)} roles for user {current_user.id}")
    return roles

@router.get("/{role_id}", response_model=RoleOut)
def get_role(
    role_id: int,
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(get_current_user)
):
    """Get a specific role by ID"""
    role = role_service.get_role_by_id(role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    return role

@router.put("/{role_id}", response_model=RoleOut)
def update_role(
    role_id: int,
    role_update: RoleUpdate,
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN))
):
    """Update a role (Admin only)"""
    role = role_service.update_role(role_id, role_update)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    logger.info(f"Role updated: {role.name} by user {current_user.id}")
    return role

@router.delete("/{role_id}")
def delete_role(
    role_id: int,
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN))
):
    """Delete a role (Admin only)"""
    success = role_service.delete_role(role_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    logger.info(f"Role deleted: {role_id} by user {current_user.id}")
    return {"detail": "Role deleted successfully"}

# Role Assignment Operations
@router.post("/assign", response_model=UserRoleOut)
def assign_role_to_user(
    assignment: UserRoleCreate,
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN))
    # current_user: User = Depends(get_current_user)
):
    """Assign a role to a user (Admin only)"""
    user_role = role_service.assign_role_to_user(
        assignment.user_id, 
        assignment.role_id, 
        current_user.id
    )
    logger.info(f"Role {assignment.role_id} assigned to user {assignment.user_id} by {current_user.id}")
    return user_role

@router.delete("/assign/{user_id}/{role_id}")
def remove_role_from_user(
    user_id: int,
    role_id: int,
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN))
):
    """Remove a role from a user (Admin only)"""
    success = role_service.remove_role_from_user(user_id, role_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role assignment not found"
        )
    logger.info(f"Role {role_id} removed from user {user_id} by {current_user.id}")
    return {"detail": "Role removed successfully"}

@router.get("/user/{user_id}", response_model=List[RoleOut])
def get_user_roles(
    user_id: int,
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(get_current_user)
):
    """Get all roles for a specific user"""
    # Users can only view their own roles unless they're admin
    if user_id != current_user.id and not current_user.has_role(RoleEnum.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this user's roles"
        )
    
    roles = role_service.get_user_roles(user_id)
    return roles

@router.get("/{role_id}/users", response_model=List[UserWithRoles])
def get_users_with_role(
    role_id: int,
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN))
):
    """Get all users with a specific role (Admin only)"""
    users = role_service.get_users_with_role(role_id)
    return users

# Bulk Operations
@router.post("/bulk-assign")
def bulk_assign_roles(
    bulk_assignment: BulkRoleAssignment,
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN))
):
    """Bulk assign roles to multiple users (Admin only)"""
    results = role_service.bulk_assign_roles(bulk_assignment, current_user.id)
    logger.info(f"Bulk role assignment completed by user {current_user.id}: {results['total_processed']} processed")
    return results

@router.post("/bulk-remove")
def bulk_remove_roles(
    bulk_removal: BulkRoleRemoval,
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN))
):
    """Bulk remove roles from multiple users (Admin only)"""
    results = role_service.bulk_remove_roles(bulk_removal)
    logger.info(f"Bulk role removal completed by user {current_user.id}: {results['total_processed']} processed")
    return results

# Utility Endpoints
@router.post("/initialize-defaults")
def initialize_default_roles(
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN))
    # current_user: User = Depends(get_current_user)
):
    """Initialize default system roles (Admin only)"""
    created_roles = role_service.create_default_roles()
    logger.info(f"Default roles initialized by user {current_user.id}: {len(created_roles)} roles created")
    return {
        "detail": f"Created {len(created_roles)} default roles",
        "roles": [{"id": role.id, "name": role.name} for role in created_roles]
    }

@router.get("/my/roles", response_model=List[RoleOut])
def get_my_roles(
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(get_current_user)
):
    """Get current user's roles"""
    roles = role_service.get_user_roles(current_user.id)
    return roles

@router.get("/my/permissions")
def get_my_permissions(
    current_user: User = Depends(get_current_user)
):
    """Get current user's permissions"""
    import json
    permissions = set()
    
    for role in current_user.roles:
        if role.permissions:
            try:
                role_permissions = json.loads(role.permissions)
                permissions.update(role_permissions)
            except (json.JSONDecodeError, TypeError):
                continue
    
    return {"permissions": list(permissions)}


@router.patch("/toggle/{role_id}", response_model=RoleOut)
def toggle_role_active(
    role_id: int = Path(..., gt=0),
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN))
):
    logger.info(f"User {current_user.id} toggled active state for role ID {role_id}")
    return role_service.toggle_role_active(role_id)



# Super Admin specific endpoints
@router.post("/assign-super-admin/{user_id}")
def assign_super_admin_role(
    user_id: int,
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(require_roles(RoleEnum.SUPER_ADMIN))
):
    """Assign super admin role to a user (Super Admin only)"""
    super_admin_role = role_service.get_role_by_name("super_admin")
    if not super_admin_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Super admin role not found"
        )
    
    user_role = role_service.assign_role_to_user(user_id, super_admin_role.id, current_user.id)
    logger.info(f"Super admin role assigned to user {user_id} by {current_user.id}")
    return {"detail": "Super admin role assigned successfully", "user_role": user_role}

@router.delete("/remove-super-admin/{user_id}")
def remove_super_admin_role(
    user_id: int,
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(require_roles(RoleEnum.SUPER_ADMIN))
):
    """Remove super admin role from a user (Super Admin only)"""
    # Prevent removing super admin from self
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove super admin role from yourself"
        )
    
    super_admin_role = role_service.get_role_by_name("super_admin")
    if not super_admin_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Super admin role not found"
        )
    
    success = role_service.remove_role_from_user(user_id, super_admin_role.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Super admin role assignment not found"
        )
    
    logger.info(f"Super admin role removed from user {user_id} by {current_user.id}")
    return {"detail": "Super admin role removed successfully"}

@router.get("/super-admins", response_model=List[UserWithRoles])
def get_super_admins(
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(require_roles(RoleEnum.SUPER_ADMIN))
):
    """Get all users with super admin role (Super Admin only)"""
    super_admin_role = role_service.get_role_by_name("super_admin")
    if not super_admin_role:
        return []
    
    users = role_service.get_users_with_role(super_admin_role.id)
    return users