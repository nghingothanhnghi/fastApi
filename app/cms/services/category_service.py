# app/cms/services/category_service.py
from typing import List, Optional
from sqlalchemy.orm import Session
from app.cms.models.category import CmsCategory
from app.cms.schemas.category import CategoryCreate, CategoryUpdate
from app.cms.utils.slugify import slugify, make_unique_slug


class CategoryService:

    def _unique_slug(self, db: Session, base: str, exclude_id: Optional[int] = None) -> str:
        def exists(slug: str) -> bool:
            q = db.query(CmsCategory).filter(CmsCategory.slug == slug)
            if exclude_id:
                q = q.filter(CmsCategory.id != exclude_id)
            return db.query(q.exists()).scalar()
        return make_unique_slug(base, exists)

    def create_category(self, db: Session, data: CategoryCreate) -> CmsCategory:
        base_slug = slugify(data.slug or data.name)
        category = CmsCategory(
            name=data.name,
            slug=self._unique_slug(db, base_slug),
            description=data.description,
            parent_id=data.parent_id,
        )
        db.add(category)
        db.commit()
        db.refresh(category)
        return category

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
        if update_data.get("slug"):
            update_data["slug"] = self._unique_slug(db, slugify(update_data["slug"]), exclude_id=category_id)
        for field, value in update_data.items():
            setattr(category, field, value)
        db.commit()
        db.refresh(category)
        return category

    def delete_category(self, db: Session, category_id: int) -> bool:
        category = self.get_category(db, category_id)
        if not category:
            return False
        db.delete(category)
        db.commit()
        return True


# ✅ Singleton instance (same convention as the rest of the codebase)
category_service = CategoryService()
