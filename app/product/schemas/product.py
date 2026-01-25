"""
Product Schemas Module

This module defines Pydantic models for request/response validation and serialization
of product and product variant data. These schemas ensure data consistency at API boundaries.

Classes:
    - ProductVariantBase: Base variant schema with common fields
    - ProductVariantCreate: Schema for creating a new product variant
    - ProductVariantResponse: Schema for variant API responses
    - ProductBase: Base product schema with common fields
    - ProductCreate: Schema for creating a new product
    - ProductUpdate: Schema for updating an existing product
    - ProductOut: Complete product schema for API responses
"""

from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime


class ProductVariantBase(BaseModel):
    """
    Base schema for product variant data.

    Attributes:
        name (str): Name/description of the variant
        sku (str | None): Stock Keeping Unit for the variant
        price (float): Price of the variant
        stock (int): Current stock quantity (default: 0)
        attributes (dict | None): JSON attributes for the variant (e.g., color, size)
        image_url (str | None): URL to the variant's image
    """

    name: str
    sku: Optional[str]
    price: float
    stock: Optional[int] = 0
    attributes: Optional[Dict] = None
    image_url: Optional[str] = None


class ProductVariantCreate(ProductVariantBase):
    """
    Schema for creating a new product variant.

    Inherits all fields from ProductVariantBase.
    Used for request validation when creating variants.
    """

    pass


class ProductVariantResponse(ProductVariantBase):
    """
    Schema for variant responses in API endpoints.

    Extends ProductVariantBase with the variant ID.
    Used for serializing variant data in API responses.

    Attributes:
        id (int): Unique identifier of the variant
    """

    id: int

    model_config = {
        "from_attributes": True
    }


class ProductBase(BaseModel):
    """
    Base schema for product data.

    Attributes:
        name (str): Product name
        description (str | None): Detailed product description
        base_price (float): Base price of the product
        sku (str | None): Stock Keeping Unit for the product
        is_active (bool): Whether the product is active (default: True)
        image_url (str | None): URL to the product's primary image
    """

    name: str
    description: Optional[str] = None
    base_price: float
    sku: Optional[str]
    is_active: Optional[bool] = True
    image_url: Optional[str] = None
    qr_code_url: Optional[str] = None


class ProductCreate(ProductBase):
    """
    Schema for creating a new product.

    Extends ProductBase with optional variants list.
    Used for request validation when creating products.

    Attributes:
        variants (list[ProductVariantCreate] | None): Variants to create with the product
    """

    variants: Optional[List[ProductVariantCreate]] = []


class ProductUpdate(BaseModel):
    """
    Schema for updating an existing product.

    All fields are optional. Only provided fields will be updated.

    Attributes:
        name (str | None): Updated product name
        description (str | None): Updated product description
        base_price (float | None): Updated base price
        sku (str | None): Updated SKU
        is_active (bool | None): Updated active status
        image_url (str | None): Updated primary image URL
        variants (list[ProductVariantCreate] | None): Replacement variants
    """

    name: Optional[str] = None
    description: Optional[str] = None
    base_price: Optional[float] = None
    sku: Optional[str] = None
    is_active: Optional[bool] = None
    image_url: Optional[str] = None
    variants: Optional[List[ProductVariantCreate]] = None


class ProductOut(ProductBase):
    """
    Complete schema for product API responses.

    Includes all product data along with metadata and variants.

    Attributes:
        id (int): Unique identifier of the product
        created_at (datetime): Timestamp when the product was created
        updated_at (datetime | None): Timestamp of last update
        variants (list[ProductVariantResponse]): Associated product variants
    """

    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    variants: List[ProductVariantResponse] = []

    model_config = {
        "from_attributes": True
    }
