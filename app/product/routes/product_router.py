"""
Product Router Module

This module defines all API endpoints for product management operations.
Routes are mounted at /products prefix and include CRUD operations for products
and variants, as well as image upload functionality.
"""

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.product.schemas.product import ProductOut, ProductCreate, ProductUpdate
from app.product.controllers.product_controller import ProductController

router = APIRouter(prefix="/products", tags=["Products"])


@router.post("", response_model=ProductOut)
def create_product(data: ProductCreate, db: Session = Depends(get_db)):
    """
    Create a new product with optional variants.

    Args:
        data (ProductCreate): Product creation details including name, price, and optional variants
        db (Session): Database session injected by FastAPI dependency

    Returns:
        ProductOut: The created product with assigned ID
    """
    return ProductController.create_product(data, db)


@router.get("", response_model=List[ProductOut])
def get_products(db: Session = Depends(get_db)):
    """
    Retrieve all products.

    Args:
        db (Session): Database session injected by FastAPI dependency

    Returns:
        list[ProductOut]: List of all products in the system
    """
    return ProductController.get_all_products(db)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a specific product by ID.

    Args:
        product_id (int): The ID of the product to retrieve
        db (Session): Database session injected by FastAPI dependency

    Returns:
        ProductOut: The requested product with its variants

    Raises:
        HTTPException: 404 if product not found
    """
    return ProductController.get_product(product_id, db)


@router.put("/{product_id}", response_model=ProductOut)
def update_product(product_id: int, data: ProductUpdate, db: Session = Depends(get_db)):
    """
    Update an existing product.

    Supports partial updates - only provided fields will be modified.

    Args:
        product_id (int): The ID of the product to update
        data (ProductUpdate): Fields to update (all optional)
        db (Session): Database session injected by FastAPI dependency

    Returns:
        ProductOut: The updated product

    Raises:
        HTTPException: 404 if product not found
    """
    return ProductController.update_product(product_id, data, db)


@router.delete("/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    """
    Delete a product and all its variants.

    Args:
        product_id (int): The ID of the product to delete
        db (Session): Database session injected by FastAPI dependency

    Returns:
        dict: Success message confirming deletion

    Raises:
        HTTPException: 404 if product not found
    """
    return ProductController.delete_product(product_id, db)


@router.post("/{product_id}/upload-image", response_model=ProductOut)
def upload_product_image(product_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Upload and save a product image.

    The image is saved to the file system and the product is updated with the image URL.

    Args:
        product_id (int): The ID of the product to upload image for
        file (UploadFile): The image file to upload
        db (Session): Database session injected by FastAPI dependency

    Returns:
        ProductOut: The updated product with new image URL

    Raises:
        HTTPException: 404 if product not found, or 400 if upload fails
    """
    return ProductController.upload_product_image(product_id, file, db)


@router.post("/variants/{variant_id}/upload-image")
def upload_variant_image(variant_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Upload and save a variant image.

    The image is saved to the file system (variants folder) and the variant
    is updated with the image URL.

    Args:
        variant_id (int): The ID of the variant to upload image for
        file (UploadFile): The image file to upload
        db (Session): Database session injected by FastAPI dependency

    Returns:
        ProductVariant: The updated variant with new image URL

    Raises:
        HTTPException: 404 if variant not found, or 400 if upload fails
    """
    return ProductController.upload_variant_image(variant_id, file, db)
