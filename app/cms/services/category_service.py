# app/cms/services/category_service.py
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.cms.models.category import CmsCategory
from app.cms.schemas.category import CategoryCreate, CategoryUpdate
from app.cms.utils.slugify import slugify, make_unique_slug, run_with_slug_retry


class CategoryService:

    def _unique_slug(self, db: Session, base: str, exclude_id: Optional[int] = None) -> str:
        def exists(slug: str) -> bool:
            q = db.query(CmsCategory).filter(CmsCategory.slug == slug)
            if exclude_id:
                q = q.filter(CmsCategory.id != exclude_id)
            return db.query(q.exists()).scalar()
        return make_unique_slug(base, exists)

    def _validate_parent(self, db: Session, parent_id: Optional[int], category_id: Optional[int] = None) -> None:
        """Parent must exist and must not be the category itself or one of its descendants."""
        if parent_id is None:
            return
        parent = self.get_category(db, parent_id)
        if not parent:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Parent category {parent_id} not found")
        if category_id is None:
            return
        seen = set()
        node = parent
        while node is not None and node.id not in seen:
            if node.id == category_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A category cannot be its own parent or a descendant of itself",
                )
            seen.add(node.id)
            node = node.parent

    def create_category(self, db: Session, data: CategoryCreate) -> CmsCategory:
        self._validate_parent(db, data.parent_id)
        base_slug = slugify(data.slug or data.name)

        def operation() -> int:
            category = CmsCategory(
                name=data.name,
                slug=self._unique_slug(db, base_slug),
                description=data.description,
                parent_id=data.parent_id,
            )
            db.add(category)
            db.commit()
            return category.id

        return self.get_category(db, run_with_slug_retry(db, operation))

    def get_category(self, db: Session, category_id: int) -> Optional[CmsCategory]:
        return db.query(CmsCategory).filter(CmsCategory.id == category_id).first()

    def get_category_by_slug(self, db: Session, slug: str) -> Optional[CmsCategory]:
        return db.query(CmsCategory).filter(CmsCategory.slug == slug).first()

    def get_all_categories(self, db: Session, parent_id: Optional[int] = None) -> List[CmsCategory]:
        query = db.query(CmsCategory)
        if parent_id is not None:
            query = query.filter(CmsCategory.parent_id == parent_id)
        return query.order_by(CmsCategory.name.asc()).all()

    def update_category(self, db: Session, category_id: int, data: CategoryUpdate) -> Optional[CmsCategory]:
        category = self.get_category(db, category_id)
        if not category:
            return None
        update_data = data.model_dump(exclude_unset=True)
        if update_data.get("parent_id") is not None:
            self._validate_parent(db, update_data["parent_id"], category_id)

        def operation() -> Optional[int]:
            obj = self.get_category(db, category_id)  # re-read: a retry follows a rollback
            if obj is None:
                return None
            values = dict(update_data)
            if values.get("slug"):
                values["slug"] = self._unique_slug(db, slugify(values["slug"]), exclude_id=category_id)
            for field, value in values.items():
                setattr(obj, field, value)
            db.commit()
            return obj.id

        saved_id = run_with_slug_retry(db, operation)
        return self.get_category(db, saved_id) if saved_id else None

    def delete_category(self, db: Session, category_id: int) -> bool:
        category = self.get_category(db, category_id)
        if not category:
            return False
        db.delete(category)
        db.commit()
        return True


# ✅ Singleton instance (same convention as the rest of the codebase)
category_service = CategoryService()
