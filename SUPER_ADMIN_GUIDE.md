# Super Admin Role Guide

This guide explains the Super Admin role implementation in the backend system.

## Overview

The Super Admin role is the highest privilege level in the system, with ultimate access to all system functions including user management, role management, and system configuration.

## Role Hierarchy

1. **Super Admin** - Ultimate system access
2. **Admin** - Full system access (but cannot manage super admins)
3. **Manager** - Management level access
4. **Moderator** - Content and user moderation
5. **User** - Standard user access

## Super Admin Features

### Permissions
- **Wildcard Permission (`*`)** - Access to all system functions
- **System Management** - Configure system settings
- **Admin Management** - Manage other administrators
- **Role Management** - Create, modify, and delete roles
- **Database Access** - Direct database operations

### Exclusive Capabilities
- Assign/remove super admin roles to/from other users
- Initialize default system roles
- Cannot remove super admin role from themselves (safety feature)

## Implementation Details

### Files Modified/Created

1. **`app/user/enums/role_enum.py`**
   - Added `SUPER_ADMIN = "super_admin"` enum value

2. **`app/user/models/user.py`**
   - Added `is_super_admin()` method
   - Added `is_admin()` method (includes super admin)
   - Enhanced `has_permission()` method with super admin logic

3. **`app/user/services/role_service.py`**
   - Added super admin to default roles creation
   - Super admin role with comprehensive permissions

4. **`app/utils/token.py`**
   - Added `get_current_super_admin()` dependency
   - Added `get_current_admin()` dependency
   - Added `require_permission()` dependency factory

5. **`app/api/endpoints/roles.py`**
   - Added super admin specific endpoints
   - Protected sensitive operations with super admin requirements

6. **`create_super_admin.py`**
   - Utility script for creating super admin roles and assignments

7. **`test_super_admin.py`**
   - Test script to verify super admin functionality

## Usage

### Creating Super Admin Role

```bash
# Create the super admin role
python create_super_admin.py --create-role

# Assign super admin role to a user by username
python create_super_admin.py --username admin_user

# Assign super admin role to a user by email
python create_super_admin.py --email admin@example.com

# List all users
python create_super_admin.py --list-users

# Create role and assign to user in one command
python create_super_admin.py --create-role --username admin_user
```

### API Endpoints

#### Super Admin Specific Endpoints

```http
# Assign super admin role to a user
POST /roles/assign-super-admin/{user_id}
Authorization: Bearer <super_admin_token>

# Remove super admin role from a user
DELETE /roles/remove-super-admin/{user_id}
Authorization: Bearer <super_admin_token>

# Get all super admins
GET /roles/super-admins
Authorization: Bearer <super_admin_token>

# Initialize default roles (super admin only)
POST /roles/initialize-defaults
Authorization: Bearer <super_admin_token>
```

#### Using Dependencies in Your Endpoints

```python
from app.utils.token import get_current_super_admin, get_current_admin, require_permission

# Require super admin access
@router.post("/sensitive-operation")
def sensitive_operation(current_user: User = Depends(get_current_super_admin)):
    # Only super admins can access this
    pass

# Require admin access (includes super admin)
@router.get("/admin-data")
def get_admin_data(current_user: User = Depends(get_current_admin)):
    # Admins and super admins can access this
    pass

# Require specific permission
@router.put("/system-config")
def update_system_config(current_user: User = Depends(require_permission("system_config"))):
    # Users with system_config permission can access this
    pass
```

### Checking Permissions in Code

```python
# Check if user is super admin
if user.is_super_admin():
    # Super admin specific logic
    pass

# Check if user is admin (includes super admin)
if user.is_admin():
    # Admin level logic
    pass

# Check specific permission
if user.has_permission("manage_system"):
    # User has system management permission
    pass
```

## Security Considerations

1. **Self-Protection**: Super admins cannot remove their own super admin role
2. **System Role Protection**: Super admin role is marked as a system role and cannot be deleted
3. **Permission Inheritance**: Super admins automatically have all permissions
4. **Audit Logging**: All super admin actions are logged

## Testing

Run the test script to verify functionality:

```bash
python test_super_admin.py
```

This will test:
- Role enum existence
- Role creation
- Permission structure
- User helper methods
- Database integrity

## Migration for Existing Systems

If you have an existing system, follow these steps:

1. **Update the database schema** (if needed):
   ```python
   from app.init_db import init_db
   init_db()  # This will create any missing tables
   ```

2. **Create default roles**:
   ```bash
   python create_super_admin.py --create-role
   ```

3. **Assign super admin to existing admin user**:
   ```bash
   python create_super_admin.py --username your_admin_username
   ```

4. **Verify the setup**:
   ```bash
   python test_super_admin.py
   ```

## Troubleshooting

### Common Issues

1. **"Super admin role not found"**
   - Run: `python create_super_admin.py --create-role`

2. **"User not found"**
   - Check username/email spelling
   - Use `--list-users` to see available users

3. **Permission denied errors**
   - Ensure the user making the request has super admin role
   - Check JWT token validity

### Debugging

Enable debug logging to see detailed information:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Best Practices

1. **Limit Super Admins**: Only assign super admin role to trusted personnel
2. **Regular Audits**: Periodically review super admin assignments
3. **Use Specific Permissions**: When possible, use specific permissions instead of admin roles
4. **Monitor Actions**: Log and monitor super admin activities
5. **Backup Strategy**: Ensure you always have at least one super admin account

## API Documentation

The super admin endpoints are automatically documented in the FastAPI Swagger UI at `/docs` when the server is running.