import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.notification import NotificationType


class NotificationOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    notification_type: NotificationType
    title: str
    message: str
    is_read: bool
    order_id: uuid.UUID | None
    created_at: datetime


class MessageCreate(BaseModel):
    order_id: uuid.UUID
    receiver_id: uuid.UUID | None = None
    content: str = Field(..., min_length=1, max_length=2000)


class MessageOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    order_id: uuid.UUID
    sender_id: uuid.UUID
    receiver_id: uuid.UUID | None
    content: str
    is_read: bool
    created_at: datetime
