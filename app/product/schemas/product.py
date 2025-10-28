from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime

class ProductVariantBase(BaseModel):
    name: str
    sku: Optional[str]
    price: float
    stock: Optional[int] = 0
    attributes: Optional[Dict] = None
    image_url: Optional[str] = None


class ProductVariantCreate(ProductVariantBase):
    pass


class ProductVariantResponse(ProductVariantBase):
    id: int

    model_config = {
        "from_attributes": True
    }


class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    base_price: float
    sku: Optional[str]
    is_active: Optional[bool] = True
    image_url: Optional[str] = None

class ProductCreate(ProductBase):
    variants: Optional[List[ProductVariantCreate]] = []


class ProductUpdate(ProductBase):
    variants: Optional[List[ProductVariantCreate]] = []


class ProductOut(ProductBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    variants: List[ProductVariantResponse] = []

    model_config = {
        "from_attributes": True
    }
