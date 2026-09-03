# app/user/bootstrap.py
# Seeds a default SUPER_ADMIN user automatically on startup if the
# users table is empty (e.g. after a fresh DB / DB wipe + restart).
# This removes the dependency on someone manually calling the public
# signup endpoint to bootstrap the first account.

import os
from datetime import datetime
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.user.models.user import User
from app.user.models.role import Role
from app.user.models.user_role import UserRole
from app.user.models.system_init import SystemInitLock
from app.user.enums.role_enum import RoleEnum
from app.user.services.role_service import RoleService
from app.user.utils.security import hash_password
from app.core.logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_ADMIN_USERNAME = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_EMAIL = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@example.com")
DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "ChangeMe123!")


def seed_default_super_admin() -> None:
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            logger.info("[Bootstrap] Users already exist — skipping default admin seed.")
            return

        # Reuse the same atomic lock the signup path uses, so this never
        # races with a concurrent manual signup on the same empty DB.
        try:
            db.add(SystemInitLock(id=1))
            db.flush()
        except IntegrityError:
            db.rollback()
            logger.info("[Bootstrap] Init lock already claimed — skipping seed.")
            return

        role_service = RoleService(db)
        role_service.create_default_roles()
        super_admin_role = db.query(Role).filter_by(name=RoleEnum.SUPER_ADMIN).first()

        db_user = User(
            client_id=str(uuid4()),
            username=DEFAULT_ADMIN_USERNAME,
            email=DEFAULT_ADMIN_EMAIL,
            hashed_password=hash_password(DEFAULT_ADMIN_PASSWORD),
            created_by_id=None,
        )
        db.add(db_user)
        db.flush()  # need db_user.id

        db.add(UserRole(
            user_id=db_user.id,
            role_id=super_admin_role.id,
            assigned_by=db_user.id,
            assigned_at=datetime.utcnow(),
        ))

        db.commit()
        logger.warning(
            f"[Bootstrap] Created default super admin '{DEFAULT_ADMIN_USERNAME}' "
            f"<{DEFAULT_ADMIN_EMAIL}>. CHANGE THE DEFAULT PASSWORD IMMEDIATELY."
        )
    except Exception as e:
        db.rollback()
        logger.error(f"[Bootstrap] Failed to seed default admin: {e}", exc_info=True)
    finally:
        db.close()