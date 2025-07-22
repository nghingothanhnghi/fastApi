# app/user/models/user_role.py
# This module defines the UserRole model for managing user roles in the system.
# It includes fields for user ID, role ID, assignment timestamp, and the user who assigned
from sqlalchemy import Column, Integer, ForeignKey, DateTime, func, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base

class UserRole(Base):
    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    assigned_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # Who assigned this role
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")
    assigned_by_user = relationship("User", foreign_keys=[assigned_by])
    
    # Ensure unique user-role combinations
    __table_args__ = (
        UniqueConstraint('user_id', 'role_id', name='unique_user_role'),
    )

    def __repr__(self):
        return f"<UserRole(user_id={self.user_id}, role_id={self.role_id})>"