# app/cms/services/menu_service.py
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.cms.models.menu import CmsMenu, CmsMenuItem, MenuItemTargetType
from app.cms.models.category import CmsCategory
from app.cms.models.post import CmsPost, PostStatus
from app.cms.schemas.menu import (
    MenuCreate, MenuUpdate, MenuItemCreate, MenuItemUpdate, MenuReorderRequest
)
from app.cms.utils.slugify import slugify, make_unique_slug, run_with_slug_retry


class MenuService:

    # ── Menus ────────────────────────────────────────────────────────────
    def _unique_slug(self, db: Session, base: str, exclude_id: Optional[int] = None) -> str:
        def exists(slug: str) -> bool:
            q = db.query(CmsMenu).filter(CmsMenu.slug == slug)
            if exclude_id:
                q = q.filter(CmsMenu.id != exclude_id)
            return db.query(q.exists()).scalar()
        return make_unique_slug(base, exists)

    def create_menu(self, db: Session, data: MenuCreate) -> CmsMenu:
        if data.location:
            existing = db.query(CmsMenu).filter(CmsMenu.location == data.location).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Menu location '{data.location}' is already in use",
                )
        base_slug = slugify(data.slug or data.name)

        def operation() -> int:
            menu = CmsMenu(name=data.name, slug=self._unique_slug(db, base_slug), location=data.location)
            db.add(menu)
            db.commit()
            return menu.id

        return self.get_menu(db, run_with_slug_retry(db, operation))

    def get_menu(self, db: Session, menu_id: int) -> Optional[CmsMenu]:
        return db.query(CmsMenu).filter(CmsMenu.id == menu_id).first()

    def get_menu_by_slug(self, db: Session, slug: str) -> Optional[CmsMenu]:
        return db.query(CmsMenu).filter(CmsMenu.slug == slug).first()

    def get_menu_by_location(self, db: Session, location: str) -> Optional[CmsMenu]:
        return db.query(CmsMenu).filter(CmsMenu.location == location).first()

    def get_all_menus(self, db: Session) -> List[CmsMenu]:
        return db.query(CmsMenu).order_by(CmsMenu.name.asc()).all()

    def update_menu(self, db: Session, menu_id: int, data: MenuUpdate) -> Optional[CmsMenu]:
        menu = self.get_menu(db, menu_id)
        if not menu:
            return None
        update_data = data.model_dump(exclude_unset=True)
        if update_data.get("location"):
            existing = db.query(CmsMenu).filter(
                CmsMenu.location == update_data["location"], CmsMenu.id != menu_id
            ).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Menu location '{update_data['location']}' is already in use",
                )

        def operation() -> Optional[int]:
            obj = self.get_menu(db, menu_id)  # re-read: a retry follows a rollback
            if obj is None:
                return None
            values = dict(update_data)
            if values.get("slug"):
                values["slug"] = self._unique_slug(db, slugify(values["slug"]), exclude_id=menu_id)
            for field, value in values.items():
                setattr(obj, field, value)
            db.commit()
            return obj.id

        saved_id = run_with_slug_retry(db, operation)
        return self.get_menu(db, saved_id) if saved_id else None

    def delete_menu(self, db: Session, menu_id: int) -> bool:
        menu = self.get_menu(db, menu_id)
        if not menu:
            return False
        db.delete(menu)  # cascade deletes items
        db.commit()
        return True

    # ── Menu items ───────────────────────────────────────────────────────
    def create_item(self, db: Session, menu_id: int, data: MenuItemCreate) -> CmsMenuItem:
        menu = self.get_menu(db, menu_id)
        if not menu:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu not found")

        if data.parent_id:
            parent = db.query(CmsMenuItem).filter(
                CmsMenuItem.id == data.parent_id, CmsMenuItem.menu_id == menu_id
            ).first()
            if not parent:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="parent_id must reference an item in the same menu",
                )

        self._validate_target(db, data.target_type, data.target_id)

        item = CmsMenuItem(menu_id=menu_id, **data.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    def get_item(self, db: Session, item_id: int) -> Optional[CmsMenuItem]:
        return db.query(CmsMenuItem).filter(CmsMenuItem.id == item_id).first()

    def update_item(self, db: Session, item_id: int, data: MenuItemUpdate) -> Optional[CmsMenuItem]:
        item = self.get_item(db, item_id)
        if not item:
            return None

        update_data = data.model_dump(exclude_unset=True)

        if "parent_id" in update_data and update_data["parent_id"] is not None:
            parent_map = {
                i.id: i.parent_id
                for i in db.query(CmsMenuItem).filter(CmsMenuItem.menu_id == item.menu_id).all()
            }
            if update_data["parent_id"] not in parent_map:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="parent_id must reference an item in the same menu",
                )
            parent_map[item_id] = update_data["parent_id"]
            self._assert_no_cycle(parent_map)

        target_type = update_data.get("target_type", item.target_type)
        target_id = update_data.get("target_id", item.target_id)
        if "target_type" in update_data or "target_id" in update_data:
            self._validate_target(db, target_type, target_id)

        for field, value in update_data.items():
            setattr(item, field, value)
        db.commit()
        db.refresh(item)
        return item

    def delete_item(self, db: Session, item_id: int) -> bool:
        item = self.get_item(db, item_id)
        if not item:
            return False
        db.delete(item)  # cascade deletes children
        db.commit()
        return True

    def reorder_items(self, db: Session, menu_id: int, data: MenuReorderRequest) -> List[CmsMenuItem]:
        """Bulk-update order/parent_id for drag-and-drop menu builders."""
        if not self.get_menu(db, menu_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu not found")
        items = db.query(CmsMenuItem).filter(CmsMenuItem.menu_id == menu_id).all()
        items_by_id = {i.id: i for i in items}
        new_parents = {i.id: i.parent_id for i in items}
        for entry in data.items:
            if entry.id in items_by_id:
                new_parents[entry.id] = entry.parent_id
        for entry in data.items:
            if entry.parent_id is not None and entry.parent_id not in items_by_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"parent_id {entry.parent_id} does not belong to menu {menu_id}",
                )
        self._assert_no_cycle(new_parents)

        for entry in data.items:
            item = items_by_id.get(entry.id)
            if not item:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Item {entry.id} does not belong to menu {menu_id}",
                )
            if entry.parent_id == entry.id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An item cannot be its own parent")
            item.parent_id = entry.parent_id
            item.order = entry.order

        db.commit()
        return self.get_menu(db, menu_id).items

    @staticmethod
    def _assert_no_cycle(parent_map: dict) -> None:
        """parent_map: {item_id: parent_id|None}. Raise 400 if following parents ever loops."""
        for start in parent_map:
            seen = set()
            node = start
            while node is not None:
                if node in seen:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Menu items cannot form a parent cycle",
                    )
                seen.add(node)
                node = parent_map.get(node)

    # ── Resolution / tree building ──────────────────────────────────────
    def _validate_target(self, db: Session, target_type: MenuItemTargetType, target_id: Optional[int]) -> None:
        if target_type == MenuItemTargetType.category:
            if not db.query(CmsCategory).filter(CmsCategory.id == target_id).first():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Category {target_id} not found")
        elif target_type == MenuItemTargetType.post:
            if not db.query(CmsPost).filter(CmsPost.id == target_id).first():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Post {target_id} not found")

    def _prefetch_slugs(self, db: Session, items: List[CmsMenuItem]) -> tuple:
        """Two queries total instead of one per item. Only *published* posts get a link."""
        cat_ids = {i.target_id for i in items if i.target_type == MenuItemTargetType.category and i.target_id}
        post_ids = {i.target_id for i in items if i.target_type == MenuItemTargetType.post and i.target_id}
        cats = (
            {c.id: c.slug for c in db.query(CmsCategory.id, CmsCategory.slug).filter(CmsCategory.id.in_(cat_ids))}
            if cat_ids else {}
        )
        posts = (
            {
                p.id: p.slug
                for p in db.query(CmsPost.id, CmsPost.slug).filter(
                    CmsPost.id.in_(post_ids), CmsPost.status == PostStatus.published
                )
            }
            if post_ids else {}
        )
        return cats, posts

    @staticmethod
    def _resolve(item: CmsMenuItem, cats: dict, posts: dict) -> Optional[str]:
        if item.target_type == MenuItemTargetType.custom:
            return item.url
        if item.target_type == MenuItemTargetType.category:
            slug = cats.get(item.target_id)
            return f"/categories/{slug}" if slug else None
        if item.target_type == MenuItemTargetType.post:
            slug = posts.get(item.target_id)
            return f"/posts/{slug}" if slug else None
        return None

    def resolve_item_url(self, db: Session, item: CmsMenuItem) -> Optional[str]:
        """Compute the actual link for a single item (prefer build_tree for many items)."""
        cats, posts = self._prefetch_slugs(db, [item])
        return self._resolve(item, cats, posts)

    def build_tree(self, db: Session, menu: CmsMenu, active_only: bool = True) -> List[dict]:
        """Build a nested dict tree (parent_id -> children) with resolved_url set."""
        items = [i for i in menu.items if (i.is_active or not active_only)]
        cats, posts = self._prefetch_slugs(db, items)
        by_parent: dict = {}
        for i in items:
            by_parent.setdefault(i.parent_id, []).append(i)
        for children in by_parent.values():
            children.sort(key=lambda i: i.order)

        def serialize(item: CmsMenuItem) -> dict:
            return {
                "id": item.id,
                "menu_id": item.menu_id,
                "label": item.label,
                "target_type": item.target_type,
                "url": item.url,
                "target_id": item.target_id,
                "parent_id": item.parent_id,
                "order": item.order,
                "open_in_new_tab": item.open_in_new_tab,
                "is_active": item.is_active,
                "resolved_url": self._resolve(item, cats, posts),
                "children": [serialize(c) for c in by_parent.get(item.id, [])],
            }

        return [serialize(i) for i in by_parent.get(None, [])]


menu_service = MenuService()
