# app/user/models/role.py
# This module defines the Role model for managing user roles in the system.
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, func
from sqlalchemy.orm import relationship
from app.database import Base

class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, index=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_system_role = Column(Boolean, default=False, nullable=False)  # For built-in roles that can't be deleted
    
    # Permissions as JSON string or you can create separate Permission model
    permissions = Column(Text, nullable=True)  # JSON string of permissions
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user_roles = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")
    
    @property
    def users(self):
        """Get all users with this role"""
        return [user_role.user for user_role in self.user_roles]

    def __repr__(self):
        return f"<Role(id={self.id}, name='{self.name}', display_name='{self.display_name}')>"