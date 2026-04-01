import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class VehicleType(str, enum.Enum):
    BICYCLE = "bicycle"
    MOTORCYCLE = "motorcycle"
    CAR = "car"
    VAN = "van"


class RiderProfile(Base):
    """
    Extended profile for users with role=RIDER.
    Tracks real-time GPS position and availability status.
    """
    __tablename__ = "rider_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False, index=True
    )
    vehicle_type: Mapped[VehicleType] = mapped_column(
        SAEnum(VehicleType, values_callable=lambda x: [e.value for e in x]),
        nullable=False, default=VehicleType.MOTORCYCLE
    )
    plate_number: Mapped[str] = mapped_column(String(20), nullable=True)

    # ── Real-time location (updated by rider app) ─────────────────────────
    current_latitude: Mapped[float] = mapped_column(Numeric(10, 7), nullable=True)
    current_longitude: Mapped[float] = mapped_column(Numeric(10, 7), nullable=True)
    location_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Operational state ─────────────────────────────────────────────────
    is_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rating: Mapped[float] = mapped_column(Numeric(3, 2), default=0.0, nullable=False)
    total_deliveries: Mapped[int] = mapped_column(default=0, nullable=False)

    # ── Bank / Payout details ─────────────────────────────────────────────
    bank_account_number: Mapped[str] = mapped_column(String(20), nullable=True)
    bank_code: Mapped[str] = mapped_column(String(10), nullable=True)
    bank_name: Mapped[str] = mapped_column(String(100), nullable=True)
    paystack_recipient_code: Mapped[str] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="rider_profile")  # noqa: F821
    orders: Mapped[list["Order"]] = relationship(  # noqa: F821
        "Order",
        back_populates="rider",
        foreign_keys="Order.rider_id",
    )

    def __repr__(self) -> str:
        return f"<RiderProfile {self.user_id} [{self.vehicle_type.value}]>"
