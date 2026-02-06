"""
Product Router Module

This module defines all API endpoints for product management operations.
Routes are mounted at /products prefix and include CRUD operations for products
and variants, as well as image upload functionality.
"""

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.core import config
from app.product.schemas.product import ProductOut, ProductCreate, ProductUpdate, ProductVariantCreate
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


# --- VARIANT ENDPOINTS ---
@router.get("/variants/skus", response_model=List[str])
def get_variant_skus(db: Session = Depends(get_db)):
    """
    Return all variant SKUs in the system so the frontend can ensure uniqueness.
    """
    return ProductController.get_all_variant_skus(db)


@router.post("/{product_id}/variants", response_model=dict)
def create_variant(product_id: int, data: ProductVariantCreate, db: Session = Depends(get_db)):
    """
    Create a new variant for a product.
    """
    return ProductController.create_variant(product_id, data, db)

@router.put("/variants/{variant_id}", response_model=dict)
def update_variant(variant_id: int, data: ProductVariantCreate, db: Session = Depends(get_db)):
    """
    Update an existing variant.
    """
    return ProductController.update_variant(variant_id, data, db)

@router.delete("/variants/{variant_id}")
def delete_variant(variant_id: int, db: Session = Depends(get_db)):
    """
    Delete a variant.
    """
    return ProductController.delete_variant(variant_id, db)

@router.post("/variants/{variant_id}/upload-image")
def upload_variant_image(variant_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Upload and save a variant image.
    """
    return ProductController.upload_variant_image(variant_id, file, db)


@router.post("/{product_id}/qr-code", response_model=ProductOut)
def regenerate_qr_code(product_id: int, db: Session = Depends(get_db)):
    """
    Regenerate the QR code for a specific product.
    """
    return ProductController.regenerate_qr_code(product_id, db)


@router.get("/{product_id}/scan")
def scan_product_qr(product_id: int, request: Request):
    """
    QR scan entrypoint.
    Always redirects to frontend product detail page.
    """

    # Backend origin (e.g. http://localhost:8000)
    backend_origin = str(request.base_url).rstrip("/")

    # DEV mapping (api → frontend)
    if "localhost:8000" in backend_origin:
        frontend_origin = "http://localhost:5173"
    else:
        # PROD: same domain (or reverse proxy handles it)
        frontend_origin = backend_origin

    redirect_url = f"{frontend_origin}/products/{product_id}"

    return RedirectResponse(url=redirect_url, status_code=302)

