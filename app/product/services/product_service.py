# app/product
"""
Product Service Module

Business logic for products and variants.

Rules enforced here (every write path uses the same checks):
  * Product SKU is unique (create AND update).
  * Variant SKU is required, trimmed, unique inside the payload, and unique
    across other products.
  * Saving a product with `variants` UPSERTS by SKU (keeps variant IDs stable)
    instead of delete-all + re-insert.
  * DB IntegrityError (race conditions) becomes a clean 409, never a raw 500.
"""

from typing import Any, Dict, Iterable, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.product.models.product import Product, ProductVariant
from app.product.schemas.product import ProductCreate, ProductUpdate, ProductVariantCreate
from app.product.services.qr_service import QRService

logger = get_logger(__name__)

_VARIANT_FIELDS = {"name", "sku", "price", "stock", "attributes", "image_url"}


class ProductService:

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _assert_product_sku_free(db: Session, sku: Optional[str], exclude_id: Optional[int] = None) -> None:
        if not sku:
            return
        q = db.query(Product.id).filter(Product.sku == sku)
        if exclude_id is not None:
            q = q.filter(Product.id != exclude_id)
        if q.first():
            logger.warning("Duplicate product SKU detected", extra={"sku": sku})
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product with SKU '{sku}' already exists.",
            )

    @staticmethod
    def _normalize_variants(
        db: Session,
        variants: Optional[Iterable[Any]],
        product_id: Optional[int] = None,
        require_full: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Turn pydantic models / dicts into clean dicts and validate SKUs.
        product_id: the product being edited (its own variants are allowed to
        keep their SKU). None when creating a new product.
        """
        rows: List[Dict[str, Any]] = []
        skus: List[str] = []

        for v in variants or []:
            data = v.model_dump() if hasattr(v, "model_dump") else dict(v)
            data = {k: val for k, val in data.items() if k in _VARIANT_FIELDS}

            sku = (data.get("sku") or "").strip()
            if not sku:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "All variants must have a SKU.")
            data["sku"] = sku

            if "name" in data:
                data["name"] = (data["name"] or "").strip()
            if require_full and not data.get("name"):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Variant '{sku}' needs a name.")

            rows.append(data)
            skus.append(sku)

        duplicates = sorted({s for s in skus if skus.count(s) > 1})
        if duplicates:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Duplicate SKU(s) in submitted variants: {', '.join(duplicates)}",
            )

        if skus:
            q = db.query(ProductVariant.sku).filter(ProductVariant.sku.in_(skus))
            if product_id is not None:
                q = q.filter(ProductVariant.product_id != product_id)
            clash = q.first()
            if clash:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"Variant SKU '{clash[0]}' already exists in another product.",
                )
        return rows

    @staticmethod
    def _commit_or_409(db: Session, message: str, log_extra: Optional[dict] = None) -> None:
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            logger.exception(message, extra=log_extra or {})
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "A product or variant with the same SKU already exists.",
            )
        except Exception:
            db.rollback()
            logger.exception(message, extra=log_extra or {})
            raise

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------
    @staticmethod
    def create_product(db: Session, data: ProductCreate):
        # 1) Validate EVERYTHING before touching the DB.
        sku = (data.sku or "").strip() or None
        ProductService._assert_product_sku_free(db, sku)
        variant_rows = ProductService._normalize_variants(db, data.variants)

        # 2) Create product.
        product = Product(
            name=data.name,
            description=data.description,
            base_price=data.base_price,
            sku=sku,
            is_active=data.is_active,
        )
        db.add(product)
        db.flush()  # get product.id

        # 3) QR code (non-fatal).
        try:
            product.qr_code_url = QRService.generate_product_qr(product.id)
        except Exception:
            logger.warning(
                "Failed to generate QR code during product creation",
                extra={"product_id": product.id},
            )

        # 4) Variants.
        for row in variant_rows:
            db.add(ProductVariant(product_id=product.id, **row))

        ProductService._commit_or_409(db, "Failed to create product", {"product_name": data.name})
        db.refresh(product)
        logger.info("Product created", extra={"product_id": product.id})
        return product

    @staticmethod
    def get_all_products(db: Session):
        products = db.query(Product).all()
        logger.info("Fetched products", extra={"count": len(products)})
        return products

    @staticmethod
    def _ensure_product(product: Optional[Product], product_id: int) -> Product:
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

        # Validate BEFORE changing anything.
        if "sku" in update_data:
            update_data["sku"] = (update_data["sku"] or "").strip() or None
            ProductService._assert_product_sku_free(db, update_data["sku"], exclude_id=product_id)

        variant_rows = None
        if variants_data is not None:
            variant_rows = ProductService._normalize_variants(
                db, variants_data, product_id=product.id, require_full=False
            )

        for field, value in update_data.items():
            setattr(product, field, value)

        if variant_rows is not None:
            ProductService._sync_variants(db, product, variant_rows)

        ProductService._commit_or_409(db, "Failed to update product", {"product_id": product_id})
        db.refresh(product)
        logger.info("Product updated", extra={"product_id": product_id})
        return product

    @staticmethod
    def delete_product(db: Session, product_id: int):
        product = ProductService.get_product_by_id(db, product_id)
        db.delete(product)
        ProductService._commit_or_409(db, "Failed to delete product", {"product_id": product_id})
        logger.info("Product deleted", extra={"product_id": product_id})
        return {"message": "Product deleted successfully"}

    # ------------------------------------------------------------------
    # Variants
    # ------------------------------------------------------------------
    @staticmethod
    def get_all_variant_skus(db: Session):
        rows = db.query(ProductVariant.sku).all()
        return [r[0] for r in rows if r[0]]

    @staticmethod
    def _sync_variants(db: Session, product: Product, rows: List[Dict[str, Any]]) -> None:
        """
        UPSERT by SKU. Existing variants keep their id (so session_items and the
        frontend don't lose references); variants missing from the payload are
        deleted; new SKUs are inserted. Does not commit.
        """
        existing = {
            v.sku: v
            for v in db.query(ProductVariant).filter(ProductVariant.product_id == product.id).all()
        }
        incoming = {r["sku"] for r in rows}

        for sku, variant in existing.items():
            if sku not in incoming:
                db.delete(variant)

        for row in rows:
            variant = existing.get(row["sku"])
            if variant:
                for key, value in row.items():
                    setattr(variant, key, value)
            else:
                if not row.get("name") or row.get("price") is None:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        f"New variant '{row['sku']}' needs a name and a price.",
                    )
                db.add(ProductVariant(product_id=product.id, **row))

        db.flush()

    @staticmethod
    def create_variant(db: Session, product_id: int, variant_data: ProductVariantCreate):
        product = ProductService.get_product_by_id(db, product_id)

        name = (variant_data.name or "").strip()
        if not name:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Variant name cannot be empty.")

        row = ProductService._normalize_variants(db, [variant_data])[0]
        row["name"] = name

        variant = ProductVariant(product_id=product.id, **row)
        db.add(variant)
        ProductService._commit_or_409(db, "Failed to create variant", {"product_id": product_id})
        db.refresh(variant)
        return variant

    @staticmethod
    def update_variant(db: Session, variant_id: int, variant_data: ProductVariantCreate):
        variant = db.query(ProductVariant).filter(ProductVariant.id == variant_id).first()
        if not variant:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Variant not found")

        sku = (variant_data.sku or "").strip()
        if not sku:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Variant SKU cannot be empty.")

        clash = (
            db.query(ProductVariant.id)
            .filter(ProductVariant.sku == sku, ProductVariant.id != variant_id)
            .first()
        )
        if clash:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Variant SKU '{sku}' already exists. Please use a different SKU.",
            )

        row = variant_data.model_dump()
        row["sku"] = sku
        for key, value in row.items():
            if key in _VARIANT_FIELDS:
                setattr(variant, key, value)

        ProductService._commit_or_409(db, "Failed to update variant", {"variant_id": variant_id})
        db.refresh(variant)
        return variant

    @staticmethod
    def delete_variant(db: Session, variant_id: int):
        variant = db.query(ProductVariant).filter(ProductVariant.id == variant_id).first()
        if not variant:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Variant not found")
        db.delete(variant)
        ProductService._commit_or_409(db, "Failed to delete variant", {"variant_id": variant_id})
        return {"message": "Variant deleted successfully"}

    @staticmethod
    def update_variant_image(db: Session, variant_id: int, image_url: str):
        variant = db.query(ProductVariant).filter(ProductVariant.id == variant_id).first()
        if not variant:
            logger.warning("Variant not found", extra={"variant_id": variant_id})
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Variant not found")
        variant.image_url = image_url
        ProductService._commit_or_409(db, "Failed to update variant image", {"variant_id": variant_id})
        db.refresh(variant)
        logger.info("Variant image updated", extra={"variant_id": variant_id})
        return variant

    @staticmethod
    def regenerate_qr_code(db: Session, product_id: int):
        product = ProductService.get_product_by_id(db, product_id)
        product.qr_code_url = QRService.generate_product_qr(product.id)
        ProductService._commit_or_409(db, "Failed to regenerate QR code", {"product_id": product_id})
        db.refresh(product)
        return product