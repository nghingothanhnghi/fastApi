# app/billiard/routes/package_router.py  (HTTP only; rules live in services/package_service.py)
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.user.enums.role_enum import RoleEnum
from app.user.models.user import User
from app.user.utils.role_requirements import require_roles
from app.user.utils.token import get_current_user
from app.billiard.schemas.package import PackageCreate, PackageOut, PackageUpdate
from app.billiard.services.package_service import package_service

router = APIRouter(prefix="/billiard/packages", tags=["Billiard Packages"])

_manager = require_roles(RoleEnum.ADMIN, RoleEnum.MANAGER)


@router.get("", response_model=list[PackageOut])
def list_packages(
    include_inactive: bool = Query(False, description="Managers' screen; the POS picker leaves it off"),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return [package_service.to_out(db, p) for p in package_service.list_packages(db, current_user, include_inactive)]


@router.get("/{package_id}", response_model=PackageOut)
def get_package(package_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return package_service.to_out(db, package_service.get_package(db, package_id, current_user))


@router.post("", response_model=PackageOut, status_code=201)
def create_package(data: PackageCreate, db: Session = Depends(get_db), current_user: User = Depends(_manager)):
    pkg = package_service.create_package(db, data, current_user)
    db.commit()
    db.refresh(pkg)
    return package_service.to_out(db, pkg)


@router.put("/{package_id}", response_model=PackageOut)
def update_package(
    package_id: int, data: PackageUpdate,
    db: Session = Depends(get_db), current_user: User = Depends(_manager),
):
    """`items` omitted keeps the list; a list replaces it. Existing bills are unaffected."""
    pkg = package_service.update_package(db, package_id, data, current_user)
    db.commit()
    db.refresh(pkg)
    return package_service.to_out(db, pkg)


@router.delete("/{package_id}", response_model=PackageOut)
def deactivate_package(package_id: int, db: Session = Depends(get_db), current_user: User = Depends(_manager)):
    """Deactivates (history kept, like tables). Reactivate with PUT {"is_active": true}."""
    pkg = package_service.deactivate_package(db, package_id, current_user)
    db.commit()
    db.refresh(pkg)
    return package_service.to_out(db, pkg)
