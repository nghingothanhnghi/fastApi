# app/api/endpoints/user.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request
from uuid import uuid4
import os
from app.core import config
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import logging
from app.database import get_db
from app.user.schemas.user import UserCreate, UserUpdate, UserOut, UserWithRoles
from app.user import user as crud_user
from app.user.enums.role_enum import RoleEnum
from app.user.utils.token import get_current_user, get_current_user_optional
from app.user.utils.role_requirements import require_roles
from app.user.models.user import User
from app.user.utils.user_helpers import add_absolute_image_url

from typing import List


router = APIRouter(prefix="/users", tags=["Users"])
logger = logging.getLogger(__name__)


# @router.post("/", response_model=UserOut)
# def create_user(
#     user: UserCreate,
#     db: Session = Depends(get_db),
#     # current_user: User = Depends(require_roles(RoleEnum.ADMIN, RoleEnum.SUPER_ADMIN))
#     current_user: User | None = Depends(get_current_user_optional),  # Allow unauthenticated for first user
#     ):
#     try:
#         user_count = db.query(User).count()

#         # 🚨 Require roles only if users already exist
#         if user_count > 0:
#             role_checker = require_roles(RoleEnum.ADMIN, RoleEnum.SUPER_ADMIN)
#             current_user = role_checker(current_user)  # raises 403 if not authorized

#         # 🆕 Pass current_user to use their client_id
#         created_user = crud_user.create_user(db, user, current_user)
#         logger.info(f"User created: {created_user.id} (client_id={created_user.client_id})")
#         return created_user
#     except IntegrityError as e:
#         db.rollback()
#         msg = str(e.orig).lower()
#         if "email" in msg:
#             detail = "Email already exists"
#         elif "username" in msg:
#             detail = "Username already exists"
#         else:
#             detail = "Duplicate entry"
#         logger.warning(f"User creation failed: {detail}")
#         raise HTTPException(status_code=400, detail=detail)

@router.post("/", response_model=UserOut)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    try:
        # If the caller sent credentials, they must be an admin creating
        # a user on behalf of someone else -> enforce role check.
        # If there's no token at all, treat this as a public self-signup
        # (or the very first bootstrap user, handled in crud_user.create_user).
        if current_user is not None:
            role_checker = require_roles(RoleEnum.ADMIN, RoleEnum.SUPER_ADMIN)
            current_user = role_checker(current_user)

        created_user = crud_user.create_user(db, user, current_user)
        logger.info(f"User created: {created_user.id} (client_id={created_user.client_id})")
        return created_user
    except IntegrityError as e:
        db.rollback()
        msg = str(e.orig).lower()
        if "email" in msg:
            detail = "Email already exists"
        elif "username" in msg:
            detail = "Username already exists"
        else:
            detail = "Duplicate entry"
        logger.warning(f"User creation failed: {detail}")
        raise HTTPException(status_code=400, detail=detail)

# GET /users/{user_id} — require auth, allow self or same-client admin/super_admin
@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
    ):
    db_user = crud_user.get_user(db, user_id)
    if not db_user:
        logger.warning(f"User not found: {user_id}")
        raise HTTPException(status_code=404, detail="User not found")  
    logger.info(f"User retrieved: {db_user.id}")

    same_tenant_admin = current_user.is_admin() and current_user.client_id == db_user.client_id
    if db_user.id != current_user.id and not current_user.is_super_admin() and not same_tenant_admin:
        raise HTTPException(403, "Not authorized")
    return add_absolute_image_url(db_user, request)

# GET /users/by-client/{client_id} — enforce tenant match unless super_admin
@router.get("/by-client/{client_id}", response_model=list[UserOut])
def get_users_by_client(
    client_id: str,
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN, RoleEnum.SUPER_ADMIN))
):
    users = crud_user.get_users_by_client(db, client_id, skip=skip, limit=limit)

    logger.info(f"{len(users)} users retrieved for client_id={client_id} (skip={skip}, limit={limit})")

    if not current_user.is_super_admin() and current_user.client_id != client_id:
        raise HTTPException(403, "Not authorized to view this client's users")

    return [add_absolute_image_url(u, request) for u in users]

# GET /users (all) — scope non-super-admin callers to their own client
@router.get("", response_model=List[UserWithRoles])
def get_all_users(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN, RoleEnum.SUPER_ADMIN))
):

    if current_user.is_super_admin():
        users = crud_user.get_all_users(db)
    else:
        users = crud_user.get_users_by_client(db, current_user.client_id)    
    return [add_absolute_image_url(u, request) for u in users]


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    user_update: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_user = crud_user.get_user(db, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    if db_user.id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this user")

    updated_user = crud_user.update_user(db, user_id, user_update)

    logger.info(f"User updated: {user_id}")
    return add_absolute_image_url(updated_user, request)

@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN))
):
    target_user = crud_user.get_user(db, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Only SUPER_ADMIN can delete across tenants; a plain ADMIN is
    # restricted to users in their own client_id.
    if not current_user.is_super_admin() and target_user.client_id != current_user.client_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this user")

    try:
        crud_user.delete_user(db, user_id)
        logger.info(f"User deleted: {user_id}")
        return {"detail": "User deleted"}
    except Exception as e:
        logger.warning(f"User deletion failed: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{user_id}/upload-image", response_model=UserOut)
def upload_user_image(
    user_id: int,
    file: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    user = crud_user.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to upload image for this user")

    # Validate file type
    allowed_extensions = (".jpg", ".jpeg", ".png", ".gif")
    if not file.filename.lower().endswith(allowed_extensions):
        raise HTTPException(status_code=400, detail="Invalid file type. Only image files are allowed.")

    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    filename = f"{uuid4().hex}_{file.filename}"
    file_path = os.path.join(config.UPLOAD_DIR, filename)

    try:
        with open(file_path, "wb") as f:
            f.write(file.file.read())
    except Exception as e:
        logger.error(f"Failed to save image for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload image")

    user.image_url = f"{config.STATIC_URL_BASE}/{filename}"

    db.commit()
    db.refresh(user)

    logger.info(f"Image uploaded for user {user.id}: {user.image_url}")
    return add_absolute_image_url(user, request)