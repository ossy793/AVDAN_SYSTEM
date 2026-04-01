import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.order import OrderStatus


# ── Cart item ─────────────────────────────────────────────────────────────────
class CartItem(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(..., gt=0, le=100)


# ── Order creation ────────────────────────────────────────────────────────────
class OrderCreate(BaseModel):
    items: list[CartItem] = Field(..., min_length=1)
    delivery_address: str = Field(..., min_length=5)
    delivery_latitude: float | None = Field(None, ge=-90, le=90)
    delivery_longitude: float | None = Field(None, ge=-180, le=180)
    delivery_notes: str | None = Field(None, max_length=500)
    # Customer specifies which hub (nearest) — optional; OMS can auto-assign
    preferred_hub_id: uuid.UUID | None = None


# ── Order item out ────────────────────────────────────────────────────────────
class OrderItemOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    quantity: int
    unit_price: float
    subtotal: float


# ── Order out ─────────────────────────────────────────────────────────────────
class OrderOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    reference: str
    customer_id: uuid.UUID
    vendor_id: uuid.UUID | None
    rider_id: uuid.UUID | None
    agent_hub_id: uuid.UUID | None
    status: OrderStatus
    subtotal: float
    delivery_fee: float
    hub_fee: float
    platform_fee: float
    total_amount: float
    delivery_address: str
    delivery_latitude: float | None
    delivery_longitude: float | None
    delivery_notes: str | None
    cancellation_reason: str | None
    dispute_reason: str | None
    items: list[OrderItemOut]
    created_at: datetime
    updated_at: datetime
    vendor_accepted_at: datetime | None
    vendor_rejected_at: datetime | None
    rider_assigned_at: datetime | None
    picked_up_at: datetime | None
    hub_verified_at: datetime | None
    in_transit_at: datetime | None
    delivered_at: datetime | None


class OrderSummary(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    reference: str
    status: OrderStatus
    total_amount: float
    delivery_address: str
    created_at: datetime


# ── Status updates ────────────────────────────────────────────────────────────
class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    reason: str | None = Field(None, max_length=500)


class OrderCancelRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)


class OrderRejectRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)


class OrderDisputeRequest(BaseModel):
    reason: str = Field(..., min_length=10, max_length=1000)


# ── Order tracking (lightweight polling response) ─────────────────────────────
class OrderTrackingOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    reference: str
    status: OrderStatus
    cancellation_reason: str | None
    # Stage timestamps — null until that stage is reached
    created_at: datetime
    vendor_accepted_at: datetime | None
    vendor_rejected_at: datetime | None
    rider_assigned_at: datetime | None
    picked_up_at: datetime | None
    hub_verified_at: datetime | None
    in_transit_at: datetime | None
    delivered_at: datetime | None


# ── Payment init response (passed back to frontend) ───────────────────────────
class OrderPaymentInit(BaseModel):
    order_id: uuid.UUID
    order_reference: str
    payment_reference: str
    checkout_url: str            # Monnify hosted checkout page
    transaction_reference: str   # Monnify transaction reference
    amount: float                # NGN
