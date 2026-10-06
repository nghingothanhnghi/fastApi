# app/billiard/models/package.py
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BilliardPackage(Base):
    __tablename__ = "billiard_packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    items = relationship("BilliardPackageItem", back_populates="package", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("client_id", "name", name="uq_package_name_per_client"),
        CheckConstraint("duration_minutes > 0 AND price >= 0", name="ck_package_positive"),
    )


class BilliardPackageItem(Base):
    __tablename__ = "billiard_package_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(
        ForeignKey("billiard_packages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # RESTRICT: deactivate a product (is_active=False) instead of deleting one a package depends on.
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    included_quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    package = relationship("BilliardPackage", back_populates="items")

    __table_args__ = (
        UniqueConstraint("package_id", "product_id", name="uq_package_product"),
        CheckConstraint("included_quantity > 0", name="ck_package_item_qty_positive"),
    )