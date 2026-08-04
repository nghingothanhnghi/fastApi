# app/cms/routes/menu_router.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.user.utils.role_requirements import require_roles
from app.user.enums.role_enum import RoleEnum
from app.cms.schemas.menu import (
    MenuCreate, MenuUpdate, MenuItemCreate, MenuItemUpdate, MenuReorderRequest
)
from app.cms.controllers.menu_controller import menu_controller

router = APIRouter(prefix="/cms/menus", tags=["CMS - Menus"])


@router.get("")
def list_menus(db: Session = Depends(get_db)):
    return menu_controller.get_all_menus(db)


@router.post("", status_code=201)
def create_menu(
    data: MenuCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MODERATOR)),
):
    return menu_controller.create_menu(db, data)


@router.get("/location/{location}")
def get_menu_by_location(
    location: str,
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
):
    """Public: fetch a menu by its fixed placement, e.g. /cms/menus/location/header"""
    return menu_controller.get_menu_by_location(db, location, active_only)


@router.get("/{menu_id}")
def get_menu(
    menu_id: int,
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
):
    return menu_controller.get_menu_with_tree(db, menu_id, active_only)


@router.put("/{menu_id}")
def update_menu(
    menu_id: int,
    data: MenuUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MODERATOR)),
):
    return menu_controller.update_menu(db, menu_id, data)


@router.delete("/{menu_id}")
def delete_menu(
    menu_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleEnum.ADMIN)),
):
    return menu_controller.delete_menu(db, menu_id)


@router.post("/{menu_id}/items", status_code=201)
def create_menu_item(
    menu_id: int,
    data: MenuItemCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MODERATOR)),
):
    return menu_controller.create_item(db, menu_id, data)


@router.put("/items/{item_id}")
def update_menu_item(
    item_id: int,
    data: MenuItemUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MODERATOR)),
):
    return menu_controller.update_item(db, item_id, data)


@router.delete("/items/{item_id}")
def delete_menu_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MODERATOR)),
):
    return menu_controller.delete_item(db, item_id)


@router.post("/{menu_id}/items/reorder")
def reorder_menu_items(
    menu_id: int,
    data: MenuReorderRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MODERATOR)),
):
    """Bulk drag-and-drop reorder: send the full flat list of {id, parent_id, order}."""
    return menu_controller.reorder_items(db, menu_id, data)