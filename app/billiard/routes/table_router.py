# app/billiard/routes/table_router.py  (HTTP only; rules live in services)
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.user.enums.role_enum import RoleEnum
from app.user.models.user import User
from app.user.utils.role_requirements import require_roles
from app.user.utils.token import get_current_user
from app.billiard.schemas.session import StartSessionResponse
from app.billiard.schemas.table import ActiveTableResponse, TableCreate, TableResponse, TableUpdate
from app.billiard.services.table_service import table_service

router = APIRouter(prefix="/tables", tags=["Billiard Tables"])


@router.post("", response_model=TableResponse, status_code=201)
def create_table(
    data: TableCreate, db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MANAGER)),
):
    table = table_service.create_table(db, data, current_user)
    db.commit()
    db.refresh(table)
    return table

@router.patch("/{table_id}", response_model=TableResponse)
def update_table(
    table_id: int,
    data: TableUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(RoleEnum.ADMIN, RoleEnum.MANAGER)
    ),
):
    table = table_service.update_table(db, table_id, data, current_user)
    db.commit()
    db.refresh(table)
    return table

@router.delete("/{table_id}")
def deactivate_table(
    table_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(RoleEnum.ADMIN, RoleEnum.MANAGER)
    ),
):
    table = table_service.deactivate_table(db, table_id, current_user)
    db.commit()
    return {
        "message": "Billiard table deactivated successfully",
        "id": table.id,
        "is_active": table.is_active,
    }

@router.post("/{table_id}/reserve", response_model=TableResponse)
def reserve_table(
    table_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MANAGER)),
):
    table = table_service.set_status(db, table_id, "reserve", current_user)
    db.commit()
    db.refresh(table)
    return table


@router.post("/{table_id}/maintenance", response_model=TableResponse)
def maintenance_table(
    table_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MANAGER)),
):
    table = table_service.set_status(db, table_id, "maintenance", current_user)
    db.commit()
    db.refresh(table)
    return table


@router.post("/{table_id}/release", response_model=TableResponse)
def release_table(
    table_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MANAGER)),
):
    table = table_service.set_status(db, table_id, "release", current_user)
    db.commit()
    db.refresh(table)
    return table


@router.get("", response_model=list[TableResponse])
def list_tables(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return table_service.list_tables(db, current_user)


@router.get("/active", response_model=list[ActiveTableResponse])
def active_tables(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return table_service.get_active_tables(db, current_user)


@router.post("/{table_id}/start", response_model=StartSessionResponse)
def start_table(table_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    session = table_service.start_session(db, table_id, current_user)
    db.commit()
    return StartSessionResponse(
        session_id=session.id, table_id=session.table_id,
        start_time=session.start_time, opened_by=current_user.username,
    )