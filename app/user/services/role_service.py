# app/user/services/role_service.py
# This module contains the RoleService class which provides methods for managing roles in the system.
# It includes functionality for creating, updating, deleting roles, assigning roles to users, and bulk operations.
# It also handles role permissions and system roles, ensuring that certain operations are restricted based on role
import json
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from fastapi import HTTPException, status

from ..models.role import Role
from ..models.user_role import UserRole
from ..models.user import User
from ..schemas.role import RoleCreate, RoleUpdate, BulkRoleAssignment, BulkRoleRemoval

import logging

logger = logging.getLogger(__name__)


class RoleService:
    def __init__(self, db: Session):
        self.db = db

    def create_role(self, role_data: RoleCreate, created_by_user_id: Optional[int] = None) -> Role:
        """Create a new role"""
        # Check if role name already exists
        existing_role = self.db.query(Role).filter(Role.name == role_data.name).first()
        if existing_role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Role with name '{role_data.name}' already exists"
            )
        
        # Convert permissions list to JSON string
        permissions_json = None
        if role_data.permissions:
            permissions_json = json.dumps(role_data.permissions)
        
        db_role = Role(
            name=role_data.name,
            display_name=role_data.display_name,
            description=role_data.description,
            is_active=role_data.is_active,
            permissions=permissions_json
        )
        
        self.db.add(db_role)
        self.db.commit()
        self.db.refresh(db_role)
        return db_role

    # def get_role_by_id(self, role_id: int) -> Optional[Role]:
    #     """Get role by ID"""
    #     return self.db.query(Role).filter(Role.id == role_id).first()
    
    def get_role_by_id(self, role_id: int) -> Optional[Role]:
        role = self.db.query(Role).filter(Role.id == role_id).first()
        if role and role.permissions:
            try:
                role.permissions = json.loads(role.permissions)
            except Exception:
                role.permissions = []
        return role

    def get_role_by_name(self, role_name: str) -> Optional[Role]:
        """Get role by name"""
        return self.db.query(Role).filter(Role.name == role_name).first()

    def get_all_roles(self, skip: int = 0, limit: int = 100, active_only: bool = False) -> List[Role]:
        """Get all roles with pagination"""
        query = self.db.query(Role)
        if active_only:
            query = query.filter(Role.is_active == True)
        return query.offset(skip).limit(limit).all()

    def update_role(self, role_id: int, role_update: RoleUpdate) -> Optional[Role]:
        """Update an existing role"""
        db_role = self.get_role_by_id(role_id)
        if not db_role:
            raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role with ID {role_id} not found"
        )
        
        # Check if role is system role and prevent certain updates
        if db_role.is_system_role and role_update.name and role_update.name != db_role.name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change name of system role"
            )
        
        # Check for name conflicts
        if role_update.name and role_update.name != db_role.name:
            existing_role = self.db.query(Role).filter(Role.name == role_update.name).first()
            if existing_role:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Role with name '{role_update.name}' already exists"
                )
        
        # Update fields
        update_data = role_update.model_dump(exclude_unset=True)
        
        # Handle permissions conversion
        if 'permissions' in update_data and update_data['permissions'] is not None:
            update_data['permissions'] = json.dumps(update_data['permissions'])
        
        for field, value in update_data.items():
            setattr(db_role, field, value)
        
        self.db.commit()
        self.db.refresh(db_role)
        return db_role
    
    def toggle_role_active(self, role_id: int) -> Role:
        """Toggle the is_active status of a role"""
        db_role = self.get_role_by_id(role_id)
        if not db_role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Role with ID {role_id} not found"
            )

        if db_role.is_system_role:
            logger.info(f"Attempt to toggle system role ID {role_id} — denied")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot toggle active status of a system role"
            )

        db_role.is_active = not db_role.is_active
        self.db.commit()
        self.db.refresh(db_role)
        logger.info(f"Toggled active state for role ID {role_id} to {db_role.is_active}")
        return db_role


    def delete_role(self, role_id: int) -> bool:
        """Delete a role (soft delete by setting is_active=False for system roles)"""
        db_role = self.get_role_by_id(role_id)
        if not db_role:
            return False
        
        if db_role.is_system_role:
            # Soft delete system roles
            db_role.is_active = False
            self.db.commit()
        else:
            # Hard delete non-system roles
            self.db.delete(db_role)
            self.db.commit()
        
        return True

    def assign_role_to_user(self, user_id: int, role_id: int, assigned_by: Optional[int] = None) -> UserRole:
        """Assign a role to a user"""
        # Check if user exists
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found"
            )
        
        # Check if role exists and is active
        role = self.db.query(Role).filter(and_(Role.id == role_id, Role.is_active == True)).first()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Active role with ID {role_id} not found"
            )
        
        # Check if assignment already exists
        existing_assignment = self.db.query(UserRole).filter(
            and_(UserRole.user_id == user_id, UserRole.role_id == role_id)
        ).first()
        
        if existing_assignment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User already has role '{role.name}'"
            )
        
        # Create assignment
        user_role = UserRole(
            user_id=user_id,
            role_id=role_id,
            assigned_by=assigned_by
        )
        
        self.db.add(user_role)
        self.db.commit()
        self.db.refresh(user_role)
        return user_role

    def remove_role_from_user(self, user_id: int, role_id: int) -> bool:
        """Remove a role from a user"""
        user_role = self.db.query(UserRole).filter(
            and_(UserRole.user_id == user_id, UserRole.role_id == role_id)
        ).first()
        
        if not user_role:
            return False
        
        self.db.delete(user_role)
        self.db.commit()
        return True

    def get_user_roles(self, user_id: int) -> List[Role]:
        """Get all roles for a specific user"""
        return self.db.query(Role).join(UserRole).filter(
            and_(UserRole.user_id == user_id, Role.is_active == True)
        ).all()

    def get_users_with_role(self, role_id: int) -> List[User]:
        """Get all users with a specific role"""
        return self.db.query(User).join(UserRole).filter(UserRole.role_id == role_id).all()

    def bulk_assign_roles(self, bulk_assignment: BulkRoleAssignment, assigned_by: Optional[int] = None) -> Dict[str, Any]:
        """Assign multiple roles to multiple users"""
        results = {
            "successful_assignments": [],
            "failed_assignments": [],
            "total_processed": 0
        }
        
        for user_id in bulk_assignment.user_ids:
            for role_id in bulk_assignment.role_ids:
                try:
                    user_role = self.assign_role_to_user(user_id, role_id, assigned_by)
                    results["successful_assignments"].append({
                        "user_id": user_id,
                        "role_id": role_id,
                        "assignment_id": user_role.id
                    })
                except HTTPException as e:
                    results["failed_assignments"].append({
                        "user_id": user_id,
                        "role_id": role_id,
                        "error": str(e.detail)
                    })
                results["total_processed"] += 1
        
        return results

    def bulk_remove_roles(self, bulk_removal: BulkRoleRemoval) -> Dict[str, Any]:
        """Remove multiple roles from multiple users"""
        results = {
            "successful_removals": [],
            "failed_removals": [],
            "total_processed": 0
        }
        
        for user_id in bulk_removal.user_ids:
            for role_id in bulk_removal.role_ids:
                success = self.remove_role_from_user(user_id, role_id)
                if success:
                    results["successful_removals"].append({
                        "user_id": user_id,
                        "role_id": role_id
                    })
                else:
                    results["failed_removals"].append({
                        "user_id": user_id,
                        "role_id": role_id,
                        "error": "Role assignment not found"
                    })
                results["total_processed"] += 1
        
        return results

    def create_default_roles(self) -> List[Role]:
        """Create default system roles"""
        default_roles = [
            {
                "name": "super_admin",
                "display_name": "Super Administrator",
                "description": "Ultimate system access with all privileges including system management",
                "permissions": ["*", "manage_system", "manage_admins", "manage_roles", "system_config", "database_access"],
                "is_system_role": True
            },
            {
                "name": "admin",
                "display_name": "Administrator",
                "description": "Full system access",
                "permissions": ["*"],  # Wildcard for all permissions
                "is_system_role": True
            },
            {
                "name": "user",
                "display_name": "Regular User",
                "description": "Standard user access",
                "permissions": ["read_profile", "update_profile"],
                "is_system_role": True
            },
            {
                "name": "moderator",
                "display_name": "Moderator",
                "description": "Moderate content and users",
                "permissions": ["read_profile", "update_profile", "moderate_content", "manage_users"],
                "is_system_role": True
            }
        ]
        
        created_roles = []
        for role_data in default_roles:
            existing_role = self.get_role_by_name(role_data["name"])
            if not existing_role:
                permissions_json = json.dumps(role_data["permissions"])
                db_role = Role(
                    name=role_data["name"],
                    display_name=role_data["display_name"],
                    description=role_data["description"],
                    permissions=permissions_json,
                    is_system_role=role_data["is_system_role"]
                )
                self.db.add(db_role)
                created_roles.append(db_role)
        
        if created_roles:
            self.db.commit()
            for role in created_roles:
                self.db.refresh(role)
        
        return created_roles
    
    
    