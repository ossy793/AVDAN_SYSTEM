import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class EscrowStatus(str, enum.Enum):
    HELD = "held"           # Funds locked pending delivery
    RELEASED = "released"   # Delivery confirmed — split to vendor + rider
    REFUNDED = "refunded"   # Order cancelled — returned to customer


class Payment(Base):
    """
    Tracks a single Paystack transaction for an order.
    One payment per order; idempotent on duplicate webhooks via reference uniqueness.
    """
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"),
        unique=True, nullable=False, index=True
    )
    # Paystack-generated reference (unique across the platform)
    reference: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    # Paystack returns amounts in kobo (NGN) — stored in naira after conversion
    currency: Mapped[str] = mapped_column(String(5), default="NGN", nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False, default=PaymentStatus.PENDING
    )
    paystack_transaction_id: Mapped[str] = mapped_column(String(100), nullable=True)
    channel: Mapped[str] = mapped_column(String(50), nullable=True)  # card / bank / ussd
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────
    order: Mapped["Order"] = relationship("Order", back_populates="payment")  # noqa: F821
    escrow: Mapped["Escrow"] = relationship(
        "Escrow", back_populates="payment", uselist=False
    )

    def __repr__(self) -> str:
        return f"<Payment {self.reference} [{self.status.value}]>"


class Escrow(Base):
    """
    Holds funds between payment confirmation and delivery confirmation.
    Released to vendor + rider wallets on DELIVERED; refunded on CANCELLED.
    """
    __tablename__ = "escrows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="CASCADE"),
        unique=True, nullable=False, index=True
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False, index=True
    )
    total_held: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    # Split amounts (populated at release time)
    vendor_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=True)
    rider_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=True)
    hub_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=True)
    platform_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=True)

    status: Mapped[EscrowStatus] = mapped_column(
        SAEnum(EscrowStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False, default=EscrowStatus.HELD
    )
    held_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    released_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────
    payment: Mapped["Payment"] = relationship("Payment", back_populates="escrow")

    def __repr__(self) -> str:
        return f"<Escrow order={self.order_id} [{self.status.value}] ₦{self.total_held}>"
