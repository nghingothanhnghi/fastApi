# app/payments/utils/permissions.py
from app.user.models.user import User


def is_manager(user: User) -> bool:
    """Managers, admins and super admins may void payments, close other people's shifts
    and resolve bank transactions."""
    return user.is_admin() or user.has_role("manager")
