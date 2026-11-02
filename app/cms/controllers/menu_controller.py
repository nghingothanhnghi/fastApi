# app/cms/controllers/menu_controller.py
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.cms.services.menu_service import menu_service
from app.cms.schemas.menu import MenuCreate, MenuUpdate, MenuItemCreate, MenuItemUpdate, MenuReorderRequest


def _menu_payload(db: Session, menu, active_only: bool = True) -> dict:
    """Explicit response body (no SQLAlchemy internals leaking via __dict__)."""
    return {
        "id": menu.id,
        "name": menu.name,
        "slug": menu.slug,
        "location": menu.location,
        "created_at": menu.created_at,
        "updated_at": menu.updated_at,
        "items": menu_service.build_tree(db, menu, active_only),
    }


class MenuController:

    @staticmethod
    def create_menu(db: Session, data: MenuCreate):
        return menu_service.create_menu(db, data)

    @staticmethod
    def get_all_menus(db: Session):
        return menu_service.get_all_menus(db)

    @staticmethod
    def get_menu_with_tree(db: Session, menu_id: int, active_only: bool = True):
        menu = menu_service.get_menu(db, menu_id)
        if not menu:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu not found")
        return _menu_payload(db, menu, active_only)

    @staticmethod
    def get_menu_by_location(db: Session, location: str, active_only: bool = True):
        menu = menu_service.get_menu_by_location(db, location)
        if not menu:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No menu found for location '{location}'")
        return _menu_payload(db, menu, active_only)

    @staticmethod
    def update_menu(db: Session, menu_id: int, data: MenuUpdate):
        menu = menu_service.update_menu(db, menu_id, data)
        if not menu:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu not found")
        return menu

    @staticmethod
    def delete_menu(db: Session, menu_id: int):
        if not menu_service.delete_menu(db, menu_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu not found")
        return {"detail": "Menu deleted successfully"}

    @staticmethod
    def create_item(db: Session, menu_id: int, data: MenuItemCreate):
        return menu_service.create_item(db, menu_id, data)

    @staticmethod
    def update_item(db: Session, item_id: int, data: MenuItemUpdate):
        item = menu_service.update_item(db, item_id, data)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found")
        return item

    @staticmethod
    def delete_item(db: Session, item_id: int):
        if not menu_service.delete_item(db, item_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found")
        return {"detail": "Menu item deleted successfully"}

    @staticmethod
    def reorder_items(db: Session, menu_id: int, data: MenuReorderRequest):
        items = menu_service.reorder_items(db, menu_id, data)
        menu = menu_service.get_menu(db, menu_id)
        return menu_service.build_tree(db, menu)


menu_controller = MenuController()