from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.product.models.product import Product, ProductVariant
from app.product.schemas.product import ProductCreate, ProductUpdate

class ProductService:
    @staticmethod
    def create_product(db: Session, data: ProductCreate):
        # 🔍 check for duplicate SKU
        if data.sku:
            existing = db.query(Product).filter(Product.sku == data.sku).first()
            if existing:
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
            variant = ProductVariant(product_id=product.id, **variant_data.dict())
            db.add(variant)

        db.commit()
        db.refresh(product)
        return product

    @staticmethod
    def get_all_products(db: Session):
        return db.query(Product).all()

    @staticmethod
    def get_product_by_id(db: Session, product_id: int):
        product = db.query(Product).filter(Product.id == product_id).first()

        return product

    @staticmethod
    def update_product(db: Session, product_id: int, data: ProductUpdate):
        product = ProductService.get_product_by_id(db, product_id)
        for field, value in data.dict(exclude_unset=True).items():
            setattr(product, field, value)
        db.commit()
        db.refresh(product)
        return product

    @staticmethod
    def delete_product(db: Session, product_id: int):
        product = ProductService.get_product_by_id(db, product_id)
        db.delete(product)
        db.commit()
        return {"message": "Product deleted successfully"}
    @staticmethod
    def update_variant_image(db: Session, variant_id: int, image_url: str):
        variant = db.query(ProductVariant).filter(ProductVariant.id == variant_id).first()
        variant.image_url = image_url
        db.commit()
        db.refresh(variant)
        return variant
    
