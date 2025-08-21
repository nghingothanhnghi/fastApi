# app/user/user.py
# This module contains functions for user management operations such as creating, updating, deleting users,
# and handling password reset codes. It interacts with the database using SQLAlchemy ORM.
from sqlalchemy.orm import Session, joinedload
from app.user.models.user import User
from app.user.models.password_reset import PasswordResetCode
from app.user.enums.role_enum import RoleEnum
from app.user.services.role_service import RoleService 
from app.user.models.role import Role
from app.user.models.user_role import UserRole
from app.user.schemas.user import UserCreate, UserUpdate
from app.user.utils.security import hash_password
from datetime import datetime, timedelta
from typing import List
import secrets
import string
from uuid import uuid4

def get_user(db: Session, user_id: int):
    return (
        db.query(User)
        .options(
            joinedload(User.created_by),
            joinedload(User.user_roles).joinedload(UserRole.role)
        )
        .filter(User.id == user_id)
        .first()
    )

def get_user_by_username(db: Session, username: str):
    return (
        db.query(User)
        .options(
            joinedload(User.created_by),
            joinedload(User.user_roles).joinedload(UserRole.role)
        )
        .filter(User.username == username)
        .first()
    )

def get_users_by_client(db: Session, client_id: str, skip: int = 0, limit: int = 100):
    return (
        db.query(User)
        .options(joinedload(User.user_roles).joinedload(UserRole.role))  # Optional: eager load roles
        .filter(User.client_id == client_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def get_all_users(db: Session):
    return (
        db.query(User)
        .options(
            joinedload(User.user_roles).joinedload(UserRole.role)  # ✅ Load roles deeply
        )
        .all()
    )

def create_user(
    db: Session, 
    user: UserCreate,
    current_user: User | None  # ⬅️ Now allows None
    ):

    role_service = RoleService(db)
    
    hashed_pw = hash_password(user.password)

    user_data = user.dict()
    user_data.pop("password")

       # ✅ Assign client_id (generate if first user)
    user_data["client_id"] = current_user.client_id if current_user else str(uuid4())
    
    # ✅ Track who created this user
    user_data["created_by_id"] = current_user.id if current_user else None

    db_user = User(**user_data, hashed_password=hashed_pw)
    db.add(db_user)
    db.flush()  # Required to get db_user.id

    total_users = db.query(User).count()

    if total_users == 1:

                # 🟢 First user: create default roles and assign SUPER_ADMIN
        role_service.create_default_roles()
        # 🚨 First user gets SUPER_ADMIN role
        super_admin_role = db.query(Role).filter_by(name=RoleEnum.SUPER_ADMIN).first()
        if super_admin_role:
            db.add(UserRole(
                user_id=db_user.id,
                role_id=super_admin_role.id,
                assigned_by=db_user.id,
                assigned_at=datetime.utcnow()
            ))
    else:
        # ✅ All other users get USER role
        user_role = db.query(Role).filter_by(name=RoleEnum.USER).first()
        if user_role:
            db.add(UserRole(
                user_id=db_user.id,
                role_id=user_role.id,
                assigned_by=(current_user.id if current_user else db_user.id),
                assigned_at=datetime.utcnow()
            ))

    db.commit()
    db.refresh(db_user)
    return db_user

def update_user(db: Session, user_id: int, user_update: UserUpdate):
    user = get_user(db, user_id)
    if not user:
        return None

    update_data = user_update.dict(exclude_unset=True)
    
    if "password" in update_data and update_data["password"]:
        from app.user.utils.security import hash_password
        update_data["hashed_password"] = hash_password(update_data.pop("password"))
    
    for key, value in update_data.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user_id: int):
    total_users = db.query(User).count()
    if total_users <= 1:
        raise Exception("Cannot delete the only remaining user in the system.")

    user = get_user(db, user_id)
    if not user:
        raise Exception("User not found.")

    db.delete(user)
    db.commit()
    return user




def save_reset_code(db: Session, email: str, code: str):
    # Delete any existing codes for this email first
    delete_reset_codes(db, email)
    
    # Create new reset code
    db_code = PasswordResetCode(email=email, code=code)
    db.add(db_code)
    db.commit()
    db.refresh(db_code)
    return db_code

def verify_reset_code(db: Session, email: str, code: str, expiry_minutes: int = 10):
    record = (
        db.query(PasswordResetCode)
        .filter(PasswordResetCode.email == email, PasswordResetCode.code == code)
        .order_by(PasswordResetCode.created_at.desc())
        .first()
    )
    if not record:
        return False

    expiry_time = record.created_at + timedelta(minutes=expiry_minutes)
    if datetime.utcnow() > expiry_time:
        return False

    return True

def delete_reset_codes(db: Session, email: str):
    db.query(PasswordResetCode).filter(PasswordResetCode.email == email).delete()
    db.commit()


def generate_reset_code() -> str:
    """Generate a secure 6-digit reset code"""
    return ''.join(secrets.choice(string.digits) for _ in range(6))


def cleanup_expired_codes(db: Session, expiry_minutes: int = 10):
    """Clean up expired reset codes"""
    expiry_time = datetime.utcnow() - timedelta(minutes=expiry_minutes)
    db.query(PasswordResetCode).filter(PasswordResetCode.created_at < expiry_time).delete()
    db.commit()