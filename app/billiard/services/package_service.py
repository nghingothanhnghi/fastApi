# app/billiard/services/package_service.py
# CRUD for BilliardPackage (a fixed price for N minutes of table time, plus products
# included for free). Same shape as pricing_rule_service. Editing or deactivating a
# package never changes an existing bill: item F makes sessions keep their own snapshot.
# Services flush; routes commit.
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billiard.models import BilliardPackage, BilliardPackageItem
from app.billiard.schemas.package import (
    PackageCreate, PackageItemIn, PackageItemOut, PackageOut, PackageUpdate,
)
from app.product.models.product import Product
from app.user.models.user import User


def _scope(stmt, user: User):
    """Tenant isolation: SUPER_ADMIN sees all, everyone else only their client_id."""
    if user.is_super_admin():
        return stmt
    return stmt.where(BilliardPackage.client_id == user.client_id)


def _duplicate_name() -> HTTPException:
    return HTTPException(409, "A package with this name already exists")


def _check_products(db: Session, items: list[PackageItemIn]) -> None:
    """400 if a product is missing or inactive. Products have no client_id (shared
    catalogue), the same as session_service.add_item."""
    for item in items:
        product = db.get(Product, item.product_id)
        if product is None:
            raise HTTPException(400, f"Product {item.product_id} not found")
        if not product.is_active:
            raise HTTPException(400, f"Product {item.product_id} is not available")


def _build_items(items: list[PackageItemIn]) -> list[BilliardPackageItem]:
    return [BilliardPackageItem(product_id=i.product_id, included_quantity=i.included_quantity) for i in items]


class PackageService:

    @staticmethod
    def list_packages(db: Session, user: User, include_inactive: bool = False) -> list[BilliardPackage]:
        stmt = select(BilliardPackage).order_by(BilliardPackage.name, BilliardPackage.id)
        if not include_inactive:
            stmt = stmt.where(BilliardPackage.is_active.is_(True))
        return list(db.execute(_scope(stmt, user)).scalars().all())

    @staticmethod
    def get_package(db: Session, package_id: int, user: User) -> BilliardPackage:
        pkg = db.execute(_scope(select(BilliardPackage).where(BilliardPackage.id == package_id), user)).scalar_one_or_none()
        if not pkg:
            raise HTTPException(404, "Package not found")      # 404 for other tenants too
        return pkg

    @staticmethod
    def _name_taken(db: Session, client_id: str, name: str, except_id: Optional[int] = None) -> bool:
        stmt = select(BilliardPackage.id).where(BilliardPackage.client_id == client_id, BilliardPackage.name == name)
        if except_id is not None:
            stmt = stmt.where(BilliardPackage.id != except_id)
        return db.execute(stmt).first() is not None

    @staticmethod
    def create_package(db: Session, data: PackageCreate, user: User) -> BilliardPackage:
        if PackageService._name_taken(db, user.client_id, data.name):
            raise _duplicate_name()
        _check_products(db, data.items)
        pkg = BilliardPackage(
            client_id=user.client_id, name=data.name, duration_minutes=data.duration_minutes,
            price=data.price, is_active=data.is_active, items=_build_items(data.items),
        )
        db.add(pkg)
        try:
            db.flush()
        except IntegrityError:          # two managers created the same name at once
            db.rollback()
            raise _duplicate_name()
        return pkg

    @staticmethod
    def update_package(db: Session, package_id: int, data: PackageUpdate, user: User) -> BilliardPackage:
        pkg = PackageService.get_package(db, package_id, user)
        changes = data.model_dump(exclude_unset=True)

        if changes.get("name") is not None and changes["name"] != pkg.name:
            if PackageService._name_taken(db, pkg.client_id, changes["name"], except_id=pkg.id):
                raise _duplicate_name()

        for field in ("name", "duration_minutes", "price", "is_active"):
            if changes.get(field) is not None:
                setattr(pkg, field, changes[field])

        if data.items is not None:                      # a list replaces the whole set
            _check_products(db, data.items)
            pkg.items.clear()
            db.flush()                                  # delete old rows before inserting, (package, product) is unique
            pkg.items.extend(_build_items(data.items))

        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise _duplicate_name()
        return pkg

    @staticmethod
    def deactivate_package(db: Session, package_id: int, user: User) -> BilliardPackage:
        """DELETE means deactivate (history kept, like tables). Safe to call twice."""
        pkg = PackageService.get_package(db, package_id, user)
        pkg.is_active = False
        db.flush()
        return pkg

    @staticmethod
    def to_out(db: Session, pkg: BilliardPackage) -> PackageOut:
        names = {}
        ids = [i.product_id for i in pkg.items]
        if ids:
            names = dict(db.execute(select(Product.id, Product.name).where(Product.id.in_(ids))).all())
        return PackageOut(
            id=pkg.id, name=pkg.name, duration_minutes=pkg.duration_minutes, price=pkg.price,
            is_active=pkg.is_active, created_at=pkg.created_at,
            items=[
                PackageItemOut(product_id=i.product_id, product_name=names.get(i.product_id),
                               included_quantity=i.included_quantity)
                for i in sorted(pkg.items, key=lambda i: i.product_id)
            ],
        )


package_service = PackageService()
