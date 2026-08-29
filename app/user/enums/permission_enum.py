class Permission(str, Enum):
    USERS_VIEW = "users.view"
    USERS_CREATE = "users.create"
    USERS_UPDATE = "users.update"
    USERS_DELETE = "users.delete"
    USERS_MANAGE_ROLES = "users.manage_roles"
    USERS_MANAGE_SUPER_ADMIN = "users.manage_super_admin"  # super_admin only
    USERS_MANAGE_STATUS = "users.manage_status"             # enable/disable
    ROLES_MANAGE = "roles.manage"