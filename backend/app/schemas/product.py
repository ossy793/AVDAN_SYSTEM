import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.product import ProductCategory


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    description: str | None = None
    category: ProductCategory = ProductCategory.OTHER
    price: float = Field(..., gt=0, description="Price in NGN")
    stock_quantity: int = Field(..., ge=0)
    image_url: str | None = Field(None, max_length=500)
    weight_kg: float | None = Field(None, gt=0)


class ProductUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    description: str | None = None
    category: ProductCategory | None = None
    price: float | None = Field(None, gt=0)
    stock_quantity: int | None = Field(None, ge=0)
    image_url: str | None = Field(None, max_length=500)
    is_available: bool | None = None
    weight_kg: float | None = Field(None, gt=0)


class ProductOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    vendor_id: uuid.UUID
    name: str
    description: str | None
    category: ProductCategory
    price: float
    stock_quantity: int
    image_url: str | None
    is_available: bool
    weight_kg: float | None
    created_at: datetime
    updated_at: datetime


class ProductListOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    vendor_id: uuid.UUID
    name: str
    category: ProductCategory
    price: float
    stock_quantity: int
    image_url: str | None
    is_available: bool
