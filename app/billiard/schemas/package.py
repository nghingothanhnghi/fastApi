# app/billiard/schemas/package.py
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_PACKAGE_MINUTES = 1440      # same ceiling as planned_minutes (timed play)


class PackageItemIn(BaseModel):
    product_id: int = Field(..., ge=1)
    included_quantity: int = Field(..., ge=1, le=1000)


def _unique_products(items: Optional[list[PackageItemIn]]) -> Optional[list[PackageItemIn]]:
    if items is not None:
        ids = [i.product_id for i in items]
        if len(ids) != len(set(ids)):
            raise ValueError("Each product can appear only once in a package")
    return items


class PackageCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    duration_minutes: int = Field(..., ge=1, le=MAX_PACKAGE_MINUTES)
    price: Decimal = Field(..., ge=0, max_digits=12, decimal_places=2,
                           description="Covers table time only, for the whole duration")
    items: list[PackageItemIn] = Field(default_factory=list, description="Products included for free")
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be blank")
        return v

    @field_validator("items")
    @classmethod
    def _items(cls, v):
        return _unique_products(v)


class PackageUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    duration_minutes: Optional[int] = Field(None, ge=1, le=MAX_PACKAGE_MINUTES)
    price: Optional[Decimal] = Field(None, ge=0, max_digits=12, decimal_places=2)
    items: Optional[list[PackageItemIn]] = Field(None, description="Omit to keep; a list REPLACES all items")
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _strip(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("name cannot be blank")
        return v

    @field_validator("items")
    @classmethod
    def _items(cls, v):
        return _unique_products(v)


class PackageItemOut(BaseModel):
    product_id: int
    product_name: Optional[str] = None
    included_quantity: int


class PackageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    duration_minutes: int
    price: Decimal
    is_active: bool
    items: list[PackageItemOut] = Field(default_factory=list)
    created_at: Optional[datetime] = None
