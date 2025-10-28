# app/product/controllers/product_controller.py
from sqlalchemy.orm import Session
from app.product.services.product_service import ProductService
from app.product.schemas.product import ProductCreate, ProductUpdate
from app.product.services.image_service import ImageService
class ProductController:
    @staticmethod
    def create_product(data: ProductCreate, db: Session):
        return ProductService.create_product(db, data)

    @staticmethod
    def get_all_products(db: Session):
        return ProductService.get_all_products(db)

    @staticmethod
    def get_product(product_id: int, db: Session):
        return ProductService.get_product_by_id(db, product_id)

    @staticmethod
    def update_product(product_id: int, data: ProductUpdate, db: Session):
        return ProductService.update_product(db, product_id, data)

    @staticmethod
    def delete_product(product_id: int, db: Session):
        return ProductService.delete_product(db, product_id)
    
    @staticmethod
    def upload_product_image(product_id: int, file, db: Session):
        url = ImageService.save_image(file)
        return ProductService.update_product(db, product_id, {"image_url": url})

    @staticmethod
    def upload_variant_image(variant_id: int, file, db: Session):
        url = ImageService.save_image(file, folder="variants")
        return ProductService.update_variant_image(db, variant_id, url)
