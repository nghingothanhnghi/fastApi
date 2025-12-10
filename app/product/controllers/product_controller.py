"""
Product Controller Module

This module contains the ProductController class which serves as the intermediary
between API routes and business logic. It handles product-related operations such as
creating, retrieving, updating, and deleting products and variants.
"""

from sqlalchemy.orm import Session
from app.product.services.product_service import ProductService
from app.product.schemas.product import ProductCreate, ProductUpdate
from app.product.services.image_service import ImageService


class ProductController:
    """
    Controller for handling product-related operations.

    This class provides static methods that coordinate between API routes and the
    ProductService layer, delegating business logic while managing image uploads.
    """

    @staticmethod
    def create_product(data: ProductCreate, db: Session):
        """
        Create a new product with optional variants.

        Args:
            data (ProductCreate): Product creation schema with product details and variants
            db (Session): Database session for ORM operations

        Returns:
            Product: The created product object with assigned ID
        """
        return ProductService.create_product(db, data)

    @staticmethod
    def get_all_products(db: Session):
        """
        Retrieve all products from the database.

        Args:
            db (Session): Database session for ORM operations

        Returns:
            list[Product]: List of all products
        """
        return ProductService.get_all_products(db)

    @staticmethod
    def get_product(product_id: int, db: Session):
        """
        Retrieve a specific product by ID.

        Args:
            product_id (int): The ID of the product to retrieve
            db (Session): Database session for ORM operations

        Returns:
            Product: The requested product object

        Raises:
            HTTPException: If product is not found (404)
        """
        return ProductService.get_product_by_id(db, product_id)

    @staticmethod
    def update_product(product_id: int, data: ProductUpdate, db: Session):
        """
        Update an existing product with new data.

        Args:
            product_id (int): The ID of the product to update
            data (ProductUpdate): Schema containing fields to update
            db (Session): Database session for ORM operations

        Returns:
            Product: The updated product object

        Raises:
            HTTPException: If product is not found (404)
        """
        return ProductService.update_product(db, product_id, data)

    @staticmethod
    def delete_product(product_id: int, db: Session):
        """
        Delete a product and all associated variants.

        Args:
            product_id (int): The ID of the product to delete
            db (Session): Database session for ORM operations

        Returns:
            dict: Success message confirming deletion

        Raises:
            HTTPException: If product is not found (404)
        """
        return ProductService.delete_product(db, product_id)

    @staticmethod
    def upload_product_image(product_id: int, file, db: Session):
        """
        Upload and save a product image, then update the product record.

        Args:
            product_id (int): The ID of the product to update with the image
            file (UploadFile): The image file to upload
            db (Session): Database session for ORM operations

        Returns:
            Product: The updated product object with new image URL

        Raises:
            HTTPException: If product is not found (404) or upload fails
        """
        url = ImageService.save_image(file)
        return ProductService.update_product(db, product_id, {"image_url": url})

    @staticmethod
    def upload_variant_image(variant_id: int, file, db: Session):
        """
        Upload and save a variant image, then update the variant record.

        Args:
            variant_id (int): The ID of the variant to update with the image
            file (UploadFile): The image file to upload
            db (Session): Database session for ORM operations

        Returns:
            ProductVariant: The updated variant object with new image URL

        Raises:
            HTTPException: If variant is not found (404) or upload fails
        """
        url = ImageService.save_image(file, folder="variants")
        return ProductService.update_variant_image(db, variant_id, url)
