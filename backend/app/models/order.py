import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class OrderStatus(str, enum.Enum):
    # ── Lifecycle ─────────────────────────────────────────────────────────
    PENDING = "pending"                   # Customer placed, awaiting payment
    PAID = "paid"                         # Payment confirmed, awaiting vendor decision
    VENDOR_CONFIRMED = "vendor_confirmed" # Vendor accepted — admin assigns rider
    VENDOR_REJECTED = "vendor_rejected"   # Vendor declined — triggers refund
    PREPARING = "preparing"               # Vendor is preparing (optional step)
    READY_FOR_PICKUP = "ready_for_pickup" # Vendor ready (optional step)
    RIDER_ASSIGNED = "rider_assigned"     # Rider assigned by admin
    PICKED_UP = "picked_up"               # Rider picked up from vendor
    AT_HUB = "at_hub"                     # Arrived at agent hub
    HUB_VERIFIED = "hub_verified"         # Agent verified & packaged
    IN_TRANSIT = "in_transit"             # Rider en route to customer
    DELIVERED = "delivered"               # Delivered to customer
    # ── Terminal states ───────────────────────────────────────────────────
    CANCELLED = "cancelled"
    DISPUTED = "disputed"
    REFUNDED = "refunded"


# Valid state transitions enforced in the service layer
VALID_TRANSITIONS: dict[OrderStatus, list[OrderStatus]] = {
    OrderStatus.PENDING:           [OrderStatus.PAID, OrderStatus.CANCELLED],
    OrderStatus.PAID:              [OrderStatus.VENDOR_CONFIRMED, OrderStatus.VENDOR_REJECTED, OrderStatus.CANCELLED],
    # Admin can assign rider directly after vendor confirms (skipping PREPARING / READY_FOR_PICKUP)
    OrderStatus.VENDOR_CONFIRMED:  [OrderStatus.RIDER_ASSIGNED, OrderStatus.PREPARING, OrderStatus.CANCELLED],
    OrderStatus.PREPARING:         [OrderStatus.READY_FOR_PICKUP, OrderStatus.RIDER_ASSIGNED, OrderStatus.CANCELLED],
    OrderStatus.READY_FOR_PICKUP:  [OrderStatus.RIDER_ASSIGNED, OrderStatus.CANCELLED],
    OrderStatus.RIDER_ASSIGNED:    [OrderStatus.PICKED_UP, OrderStatus.CANCELLED],
    OrderStatus.PICKED_UP:         [OrderStatus.AT_HUB],
    OrderStatus.AT_HUB:            [OrderStatus.HUB_VERIFIED],
    OrderStatus.HUB_VERIFIED:      [OrderStatus.IN_TRANSIT],
    OrderStatus.IN_TRANSIT:        [OrderStatus.DELIVERED, OrderStatus.DISPUTED],
    OrderStatus.DELIVERED:         [],
    OrderStatus.VENDOR_REJECTED:   [OrderStatus.REFUNDED],
    OrderStatus.CANCELLED:         [OrderStatus.REFUNDED],
    OrderStatus.DISPUTED:          [OrderStatus.DELIVERED, OrderStatus.REFUNDED],
    OrderStatus.REFUNDED:          [],
}


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Human-readable reference: ADV-YYYYMMDD-XXXXX
    reference: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False, index=True
    )

    # ── Actors ────────────────────────────────────────────────────────────
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor_profiles.id"), nullable=True, index=True
    )
    rider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rider_profiles.id"), nullable=True, index=True
    )
    agent_hub_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_hubs.id"), nullable=True, index=True
    )

    # ── Financial ─────────────────────────────────────────────────────────
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    delivery_fee: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    hub_fee: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    platform_fee: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    # ── Delivery ──────────────────────────────────────────────────────────
    delivery_address: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_latitude: Mapped[float] = mapped_column(Numeric(10, 7), nullable=True)
    delivery_longitude: Mapped[float] = mapped_column(Numeric(10, 7), nullable=True)
    delivery_notes: Mapped[str] = mapped_column(Text, nullable=True)

    # ── Status & tracking ─────────────────────────────────────────────────
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False, default=OrderStatus.PENDING, index=True
    )
    cancellation_reason: Mapped[str] = mapped_column(Text, nullable=True)
    dispute_reason: Mapped[str] = mapped_column(Text, nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Stage-level timestamps for tracking
    vendor_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    vendor_rejected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    rider_assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    picked_up_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    hub_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    in_transit_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────
    customer: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="customer_orders", foreign_keys=[customer_id]
    )
    vendor: Mapped["VendorProfile"] = relationship(  # noqa: F821
        "VendorProfile", back_populates="orders", foreign_keys=[vendor_id]
    )
    rider: Mapped["RiderProfile"] = relationship(  # noqa: F821
        "RiderProfile", back_populates="orders", foreign_keys=[rider_id]
    )
    agent_hub: Mapped["AgentHub"] = relationship(  # noqa: F821
        "AgentHub", back_populates="orders", foreign_keys=[agent_hub_id]
    )
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )
    payment: Mapped["Payment"] = relationship(  # noqa: F821
        "Payment", back_populates="order", uselist=False
    )
    messages: Mapped[list["Message"]] = relationship(  # noqa: F821
        "Message", back_populates="order"
    )

    def can_transition_to(self, new_status: OrderStatus) -> bool:
        return new_status in VALID_TRANSITIONS.get(self.status, [])

    def __repr__(self) -> str:
        return f"<Order {self.reference} [{self.status.value}]>"


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=False
    )
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)  # snapshot
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)  # snapshot
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    # ── Relationships ─────────────────────────────────────────────────────
    order: Mapped["Order"] = relationship("Order", back_populates="items")
    product: Mapped["Product"] = relationship(  # noqa: F821
        "Product", back_populates="order_items"
    )

    def __repr__(self) -> str:
        return f"<OrderItem {self.product_name} x{self.quantity}>"
