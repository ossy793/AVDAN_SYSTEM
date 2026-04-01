import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.payment import PaymentStatus, EscrowStatus


class PaymentOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    order_id: uuid.UUID
    reference: str
    amount: float
    currency: str
    status: PaymentStatus
    channel: str | None
    paid_at: datetime | None
    created_at: datetime


class EscrowOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    order_id: uuid.UUID
    total_held: float
    vendor_amount: float | None
    rider_amount: float | None
    hub_amount: float | None
    platform_amount: float | None
    status: EscrowStatus
    held_at: datetime
    released_at: datetime | None


# ── Payout request ────────────────────────────────────────────────────────────
class PayoutRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Amount to withdraw in NGN")
    reason: str | None = Field("Earnings withdrawal", max_length=200)


class PayoutResponse(BaseModel):
    reference: str
    amount: float
    status: str
    message: str


# ── Monnify webhook payload (we only deserialise what we need) ────────────────
class MonnifyEvent(BaseModel):
    eventType: str
    eventData: dict
