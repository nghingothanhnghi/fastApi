# app/cms/controllers/category_controller.py
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.cms.services.category_service import category_service
from app.cms.schemas.category import CategoryCreate, CategoryUpdate


class CategoryController:

    @staticmethod
    def create_category(db: Session, data: CategoryCreate):
        return category_service.create_category(db, data)

    @staticmethod
    def get_category(db: Session, category_id: int):
        category = category_service.get_category(db, category_id)
        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
        return category

    @staticmethod
    def get_category_by_slug(db: Session, slug: str):
        category = category_service.get_category_by_slug(db, slug)
        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
        return category

    @staticmethod
    def get_all_categories(db: Session, parent_id: Optional[int] = None):
        return category_service.get_all_categories(db, parent_id)

    @staticmethod
    def update_category(db: Session, category_id: int, data: CategoryUpdate):
        category = category_service.update_category(db, category_id, data)
        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
        return category

    @staticmethod
    def delete_category(db: Session, category_id: int, reassign_to: Optional[int] = None):
        result = category_service.delete_category(db, category_id, reassign_to)
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
        return result


category_controller = CategoryController()
