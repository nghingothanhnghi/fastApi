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
from app.product.schemas.product import ProductCreate, ProductUpdate, ProductVariantCreate
from app.product.services.qr_service import QRService
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
        
        # Generate QR code
        try:
            product.qr_code_url = QRService.generate_product_qr(product.id)
        except Exception:
            logger.warning("Failed to generate QR code during product creation", extra={"product_id": product.id})

        for variant_data in data.variants or []:
            variant = ProductVariant(product_id=product.id, **variant_data.model_dump())
            db.add(variant)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to create product", extra={"product_name": data.name})
            raise
        db.refresh(product)
        logger.info("Product created", extra={"product_id": product.id})
        return product

    @staticmethod
    def get_all_products(db: Session):
        products = db.query(Product).all()
        logger.info("Fetched products", extra={"count": len(products)})
        return products

    @staticmethod
    def _ensure_product(product: Product | None, product_id: int) -> Product:
        if not product:
            logger.warning("Product not found", extra={"product_id": product_id})
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        return product

    @staticmethod
    def get_product_by_id(db: Session, product_id: int):
        product = db.query(Product).filter(Product.id == product_id).first()
        return ProductService._ensure_product(product, product_id)

    @staticmethod
    def _prepare_update_data(data: Any) -> Dict[str, Any]:

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
    def delete_product(db: Session, product_id: int):
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

       # --- VARIANT METHODS ---
    @staticmethod
    def get_all_variant_skus(db: Session):
        rows = db.query(ProductVariant.sku).all()
        return [r[0] for r in rows if r[0]]

    @staticmethod
    def create_variant(db: Session, product_id: int, variant_data: ProductVariantCreate):
        product = ProductService.get_product_by_id(db, product_id)

        # Trim inputs
        name = (variant_data.name or "").strip()
        sku = (variant_data.sku or "").strip()

        # --- Validate required fields ---
        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Variant name cannot be empty."
            )
    
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Variant SKU cannot be empty."
            )

        existing = db.query(ProductVariant).filter(ProductVariant.sku == sku).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Variant SKU '{sku}' already exists. Please use a different SKU."
            )

        # Assign trimmed values back
        variant_data.name = name
        variant_data.sku = sku  # assign cleaned SKU

        variant = ProductVariant(product_id=product.id, **variant_data.model_dump())
        db.add(variant)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create variant due to a server error."
            )
        db.refresh(variant)
        return variant

    @staticmethod
    def update_variant(db: Session, variant_id: int, variant_data: ProductVariantCreate):
        variant = db.query(ProductVariant).filter(ProductVariant.id == variant_id).first()
        if not variant:
            raise HTTPException(status_code=404, detail="Variant not found")

        # --- Validation: SKU required and unique if changed ---
        sku = (variant_data.sku or "").strip()
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Variant SKU cannot be empty."
            )

        existing = db.query(ProductVariant).filter(ProductVariant.sku == sku).first()
        if existing and existing.id != variant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Variant SKU '{sku}' already exists. Please use a different SKU."
            )

        variant_data.sku = sku
        for k, v in variant_data.model_dump().items():
            setattr(variant, k, v)

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update variant due to a server error."
            )

        db.refresh(variant)
        return variant

    @staticmethod
    def delete_variant(db: Session, variant_id: int):
        variant = db.query(ProductVariant).filter(ProductVariant.id == variant_id).first()
        if not variant:
            raise HTTPException(status_code=404, detail="Variant not found")
        db.delete(variant)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        return {"message": "Variant deleted successfully"}    

    
    @staticmethod
    def _replace_variants(db: Session, product: Product, variants_data: Iterable[Any]):
        incoming_skus = []
        for v in variants_data or []:
            sku = v.sku.strip() if isinstance(v, ProductVariantCreate) else v.get("sku", "").strip()
            if not sku:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="All variants must have a SKU."
                )
            incoming_skus.append(sku)

        # Check duplicates in payload
        duplicates = set([sku for sku in incoming_skus if incoming_skus.count(sku) > 1])
        if duplicates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate SKU(s) in submitted variants: {', '.join(duplicates)}"
            )

        # Check duplicates in DB (other products)
        for sku in incoming_skus:
            existing = db.query(ProductVariant).filter(ProductVariant.sku == sku).first()
            if existing and existing.product_id != product.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Variant SKU '{sku}' already exists in another product."
                )

        # Delete old variants and add new ones
        db.query(ProductVariant).filter(ProductVariant.product_id == product.id).delete()
        for variant_data in variants_data or []:
            payload = variant_data.model_dump() if isinstance(variant_data, ProductVariantCreate) else variant_data
            db.add(ProductVariant(product_id=product.id, **payload))

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to replace variants due to a server error."
            )

    @staticmethod
    def update_variant_image(db: Session, variant_id: int, image_url: str):
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

    @staticmethod
    def regenerate_qr_code(db: Session, product_id: int):
        product = ProductService.get_product_by_id(db, product_id)
        product.qr_code_url = QRService.generate_product_qr(product.id)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to regenerate QR code", extra={"product_id": product_id})
            raise
        db.refresh(product)
        return product
