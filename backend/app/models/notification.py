import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class NotificationType(str, enum.Enum):
    ORDER_PLACED = "order_placed"
    ORDER_CONFIRMED = "order_confirmed"
    ORDER_READY = "order_ready"
    RIDER_ASSIGNED = "rider_assigned"
    ORDER_PICKED_UP = "order_picked_up"
    ORDER_AT_HUB = "order_at_hub"
    ORDER_IN_TRANSIT = "order_in_transit"
    ORDER_DELIVERED = "order_delivered"
    ORDER_CANCELLED = "order_cancelled"
    PAYMENT_RECEIVED = "payment_received"
    PAYOUT_INITIATED = "payout_initiated"
    PAYOUT_SUCCESS = "payout_success"
    DISPUTE_OPENED = "dispute_opened"
    GENERAL = "general"


class Notification(Base):
    """In-app notification. Extended by SMS/WhatsApp via the notification service."""
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        SAEnum(NotificationType, values_callable=lambda x: [e.value for e in x]),
        nullable=False, default=NotificationType.GENERAL
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # ── Relationships ─────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="notifications")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Notification {self.notification_type.value} → user={self.user_id}>"


class Message(Base):
    """
    In-app chat message tied to an order.
    Participants: customer, vendor, rider, agent, admin.
    """
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    receiver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # ── Relationships ─────────────────────────────────────────────────────
    sender: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="sent_messages", foreign_keys=[sender_id]
    )
    receiver: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="received_messages", foreign_keys=[receiver_id]
    )
    order: Mapped["Order"] = relationship("Order", back_populates="messages")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Message order={self.order_id} from={self.sender_id}>"
