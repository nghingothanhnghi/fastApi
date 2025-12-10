"""
Product Service Module

This module contains the ProductService class which implements the business logic
for product management operations. It handles database interactions, validation,
and error handling for product and variant operations.
"""

from typing import Any, Dict, Iterable
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.product.models.product import Product, ProductVariant
from app.product.schemas.product import ProductCreate, ProductUpdate
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class ProductService:
    """
    Service layer for product management operations.

    This class provides static methods for CRUD operations on products and variants,
    including validation, error handling, and logging.
    """
    @staticmethod
    def create_product(db: Session, data: ProductCreate):
        """
        Create a new product with validation and optional variants.

        Validates that the SKU is unique if provided, creates the product record,
        and then creates any associated variants in a single transaction.

        Args:
            db (Session): Database session for ORM operations
            data (ProductCreate): Product creation schema with details and variants

        Returns:
            Product: The created product object with assigned ID

        Raises:
            HTTPException: If SKU is duplicate (400)
        """
        if data.sku:
            existing = db.query(Product).filter(Product.sku == data.sku).first()
            if existing:
                logger.warning("Duplicate SKU detected", extra={"sku": data.sku})
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Product with SKU '{data.sku}' already exists."
                )
        product = Product(
            name=data.name,
            description=data.description,
            base_price=data.base_price,
            sku=data.sku,
            is_active=data.is_active
        )
        db.add(product)
        db.flush()
        for variant_data in data.variants or []:
            variant = ProductVariant(product_id=product.id, **variant_data.model_dump())
            db.add(variant)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to create product", extra={"name": data.name})
            raise
        db.refresh(product)
        logger.info("Product created", extra={"product_id": product.id})
        return product

    @staticmethod
    def get_all_products(db: Session):
        """
        Retrieve all products from the database.

        Args:
            db (Session): Database session for ORM operations

        Returns:
            list[Product]: List of all products in the database
        """
        products = db.query(Product).all()
        logger.info("Fetched products", extra={"count": len(products)})
        return products

    @staticmethod
    def _ensure_product(product: Product | None, product_id: int) -> Product:
        """
        Validate that a product exists, raising an exception if not.

        Args:
            product (Product | None): The product object to validate
            product_id (int): The product ID for error logging

        Returns:
            Product: The validated product object

        Raises:
            HTTPException: If product is None (404)
        """
        if not product:
            logger.warning("Product not found", extra={"product_id": product_id})
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        return product

    @staticmethod
    def get_product_by_id(db: Session, product_id: int):
        """
        Retrieve a specific product by ID.

        Args:
            db (Session): Database session for ORM operations
            product_id (int): The ID of the product to retrieve

        Returns:
            Product: The requested product object

        Raises:
            HTTPException: If product is not found (404)
        """
        product = db.query(Product).filter(Product.id == product_id).first()
        return ProductService._ensure_product(product, product_id)

    @staticmethod
    def _prepare_update_data(data: Any) -> Dict[str, Any]:
        """
        Convert update data to a dictionary, filtering out None values.

        Handles multiple input formats: ProductUpdate schema, dict, or iterable.
        Only includes fields that are explicitly set (excludes unset fields).

        Args:
            data (Any): Update data in various formats (ProductUpdate, dict, or iterable)

        Returns:
            dict: Cleaned dictionary with non-None values

        Raises:
            HTTPException: If data format is invalid (400)
        """
        if isinstance(data, ProductUpdate):
            payload = data.model_dump(exclude_unset=True, exclude_none=True)
        elif isinstance(data, dict):
            payload = {k: v for k, v in data.items() if v is not None}
        elif isinstance(data, Iterable):
            payload = {k: v for k, v in dict(data).items() if v is not None}
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid update payload")
        return payload

    @staticmethod
    def update_product(db: Session, product_id: int, data: Any):
        """
        Update an existing product with new data.

        Updates product fields and optionally replaces variants if provided.
        Only updates fields that are explicitly provided (partial updates supported).

        Args:
            db (Session): Database session for ORM operations
            product_id (int): The ID of the product to update
            data (Any): Update data (ProductUpdate, dict, or other iterable format)

        Returns:
            Product: The updated product object

        Raises:
            HTTPException: If product is not found (404) or update fails
        """
        product = ProductService.get_product_by_id(db, product_id)
        update_data = ProductService._prepare_update_data(data)
        variants_data = update_data.pop("variants", None)
        for field, value in update_data.items():
            setattr(product, field, value)
        if variants_data is not None:
            ProductService._replace_variants(db, product, variants_data)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to update product", extra={"product_id": product_id})
            raise
        db.refresh(product)
        logger.info("Product updated", extra={"product_id": product_id})
        return product

    @staticmethod
    def _replace_variants(db: Session, product: Product, variants_data: Iterable[Dict[str, Any]]):
        """
        Replace all variants for a product with new variant data.

        Deletes existing variants and creates new ones. Used when updating variants
        as part of a product update operation.

        Args:
            db (Session): Database session for ORM operations
            product (Product): The product object to update variants for
            variants_data (Iterable): Iterable of variant data dictionaries or objects
        """
        db.query(ProductVariant).filter(ProductVariant.product_id == product.id).delete()
        for variant_data in variants_data or []:
            if isinstance(variant_data, dict):
                payload = variant_data
            else:
                payload = variant_data.model_dump(exclude_none=True)
            variant = ProductVariant(product_id=product.id, **payload)
            db.add(variant)

    @staticmethod
    def delete_product(db: Session, product_id: int):
        """
        Delete a product and all its associated variants.

        Cascading delete is handled by the database relationship configuration
        (cascade="all, delete" on the Product model).

        Args:
            db (Session): Database session for ORM operations
            product_id (int): The ID of the product to delete

        Returns:
            dict: Success message confirming deletion

        Raises:
            HTTPException: If product is not found (404)
        """
        product = ProductService.get_product_by_id(db, product_id)
        db.delete(product)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to delete product", extra={"product_id": product_id})
            raise
        logger.info("Product deleted", extra={"product_id": product_id})
        return {"message": "Product deleted successfully"}

    @staticmethod
    def update_variant_image(db: Session, variant_id: int, image_url: str):
        """
        Update the image URL for a specific product variant.

        Args:
            db (Session): Database session for ORM operations
            variant_id (int): The ID of the variant to update
            image_url (str): The new image URL for the variant

        Returns:
            ProductVariant: The updated variant object

        Raises:
            HTTPException: If variant is not found (404)
        """
        variant = db.query(ProductVariant).filter(ProductVariant.id == variant_id).first()
        if not variant:
            logger.warning("Variant not found", extra={"variant_id": variant_id})
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
        variant.image_url = image_url
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to update variant image", extra={"variant_id": variant_id})
            raise
        db.refresh(variant)
        logger.info("Variant image updated", extra={"variant_id": variant_id})
        return variant
