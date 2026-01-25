"""
Product Models Module

This module contains SQLAlchemy ORM models for managing product data and product variants.
It defines the database schema and relationships for products and their variants.

Classes:
    - Product: Represents a base product with general information
    - ProductVariant: Represents product variations with specific pricing and stock
"""

from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean, JSON, DateTime, func
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime
from sqlalchemy.sql import func


class Product(Base):
    """
    Product model representing a product in the inventory system.

    Attributes:
        id (int): Unique identifier for the product (Primary Key)
        name (str): Product name (max 255 characters)
        description (str): Detailed product description (max 1024 characters)
        base_price (float): Base price of the product
        sku (str): Stock Keeping Unit - unique product code for inventory tracking
        is_active (bool): Indicates whether the product is active (default: True)
        image_url (str): URL to the product's primary image
        created_at (datetime): Timestamp when the product was created
        updated_at (datetime): Timestamp when the product was last updated
        variants (relationship): Collection of ProductVariant objects associated with this product
    """

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(String(1024))
    base_price = Column(Float, nullable=False)
    sku = Column(String(100), unique=True, index=True)
    is_active = Column(Boolean, default=True)
    image_url = Column(String(255), nullable=True)
    qr_code_url = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete")


class ProductVariant(Base):
    """
    ProductVariant model representing different variations of a product.

    A product can have multiple variants (e.g., different colors, sizes) with different
    prices and stock levels. Each variant is linked to a parent Product.

    Attributes:
        id (int): Unique identifier for the variant (Primary Key)
        product_id (int): Foreign Key referencing the parent Product
        name (str): Name/description of the variant (e.g., "Red Medium")
        sku (str): Unique SKU for the specific variant
        price (float): Price specific to this variant
        stock (int): Current stock quantity for this variant (default: 0)
        attributes (dict): JSON object storing variant-specific attributes (e.g., {"color": "red", "size": "M"})
        image_url (str): URL to the variant's specific image
        product (relationship): Reference to the parent Product object
        created_at (datetime): Timestamp when the variant was created
        updated_at (datetime): Timestamp when the variant was last updated
    """

    __tablename__ = "product_variants"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"))
    name = Column(String(255), nullable=False)
    sku = Column(String(100), unique=True)
    price = Column(Float, nullable=False)
    stock = Column(Integer, default=0)
    attributes = Column(JSON, nullable=True)
    image_url = Column(String(255), nullable=True)

    product = relationship("Product", back_populates="variants")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
