from typing import Any, Dict, Iterable
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.product.models.product import Product, ProductVariant
from app.product.schemas.product import ProductCreate, ProductUpdate
from app.core.logging_config import get_logger

logger = get_logger(__name__)

class ProductService:
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
    def _replace_variants(db: Session, product: Product, variants_data: Iterable[Dict[str, Any]]):
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
