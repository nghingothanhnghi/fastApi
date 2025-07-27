# app/user/models/user.py
from sqlalchemy import Column, Integer, Float, DateTime, String, func, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(String, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    phone_number = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)

    hashed_password = Column(String, nullable=False)

    
    # ✅ New image field
    image_url = Column(String, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

 
    # ✅ Relationship to creator
    created_by = relationship("User", remote_side=[id], backref="created_users")

    # Relationships
    user_roles = relationship("UserRole", foreign_keys="UserRole.user_id", back_populates="user", cascade="all, delete-orphan")

    devices_hydro = relationship("HydroDevice", back_populates="user", cascade="all, delete-orphan")
    @property
    def roles(self):
        """Get all roles for this user"""
        return [user_role.role for user_role in self.user_roles if user_role.role.is_active]
    
    def has_role(self, role_name: str) -> bool:
        """Check if user has a specific role"""
        return any(role.name == role_name for role in self.roles)
    
    def is_super_admin(self) -> bool:
        """Check if user is a super admin"""
        return self.has_role("super_admin")
    
    def is_admin(self) -> bool:
        """Check if user is an admin (including super admin)"""
        return self.has_role("super_admin") or self.has_role("admin")
    
    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission through any of their roles"""
        import json
        # Super admin has all permissions
        if self.is_super_admin():
            return True
            
        for role in self.roles:
            if role.permissions:
                try:
                    permissions = json.loads(role.permissions)
                    if "*" in permissions or permission in permissions:
                        return True
                except (json.JSONDecodeError, TypeError):
                    continue
        return False