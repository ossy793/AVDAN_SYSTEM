import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class VendorProfile(Base):
    """
    Extended profile for users with role=VENDOR.
    Stores business details and Paystack transfer recipient info for payouts.
    """
    __tablename__ = "vendor_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False, index=True
    )
    business_name: Mapped[str] = mapped_column(String(200), nullable=False)
    business_address: Mapped[str] = mapped_column(Text, nullable=False)
    business_type: Mapped[str] = mapped_column(String(100), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str] = mapped_column(String(500), nullable=True)

    # ── Bank / Payout details ─────────────────────────────────────────────
    bank_account_number: Mapped[str] = mapped_column(String(20), nullable=True)
    bank_code: Mapped[str] = mapped_column(String(10), nullable=True)
    bank_name: Mapped[str] = mapped_column(String(100), nullable=True)
    # Paystack transfer recipient code (created via /transferrecipient)
    paystack_recipient_code: Mapped[str] = mapped_column(String(100), nullable=True)

    # ── Location ──────────────────────────────────────────────────────────
    latitude: Mapped[float] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[float] = mapped_column(Numeric(10, 7), nullable=True)

    # ── Status ────────────────────────────────────────────────────────────
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rating: Mapped[float] = mapped_column(Numeric(3, 2), default=0.0, nullable=False)
    total_orders: Mapped[int] = mapped_column(default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="vendor_profile")  # noqa: F821
    products: Mapped[list["Product"]] = relationship(  # noqa: F821
        "Product", back_populates="vendor", cascade="all, delete-orphan"
    )
    orders: Mapped[list["Order"]] = relationship(  # noqa: F821
        "Order",
        back_populates="vendor",
        foreign_keys="Order.vendor_id",
    )

    def __repr__(self) -> str:
        return f"<VendorProfile {self.business_name}>"
