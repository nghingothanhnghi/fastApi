# app/user/enums/role_enum.py
# Define the role enumeration class
from enum import Enum

class RoleEnum(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    USER = "user"
    MANAGER = "manager"
    MODERATOR = "moderator"
    # Add more roles as needed
