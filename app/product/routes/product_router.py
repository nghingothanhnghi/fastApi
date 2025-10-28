from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.product.schemas.product import ProductOut, ProductCreate, ProductUpdate
from app.product.controllers.product_controller import ProductController

router = APIRouter(prefix="/products", tags=["Products"])

@router.post("/", response_model=ProductOut)
def create_product(data: ProductCreate, db: Session = Depends(get_db)):
    return ProductController.create_product(data, db)

@router.get("/", response_model=List[ProductOut])
def get_products(db: Session = Depends(get_db)):
    return ProductController.get_all_products(db)

@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    return ProductController.get_product(product_id, db)

@router.put("/{product_id}", response_model=ProductOut)
def update_product(product_id: int, data: ProductUpdate, db: Session = Depends(get_db)):
    return ProductController.update_product(product_id, data, db)

@router.delete("/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    return ProductController.delete_product(product_id, db)

# ✅ Upload product image
@router.post("/{product_id}/upload-image", response_model=ProductOut)
def upload_product_image(product_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    return ProductController.upload_product_image(product_id, file, db)

# ✅ Upload variant image
@router.post("/variants/{variant_id}/upload-image")
def upload_variant_image(variant_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    return ProductController.upload_variant_image(variant_id, file, db)
