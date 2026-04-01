import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    CUSTOMER = "customer"
    VENDOR = "vendor"
    RIDER = "rider"
    AGENT = "agent"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    phone: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, values_callable=lambda x: [e.value for e in x]),
        nullable=False, index=True
    )
    # Additional roles beyond the primary role (e.g. a customer who is also a vendor)
    extra_roles: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────
    wallet: Mapped["Wallet"] = relationship(  # noqa: F821
        "Wallet", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    vendor_profile: Mapped["VendorProfile"] = relationship(  # noqa: F821
        "VendorProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    rider_profile: Mapped["RiderProfile"] = relationship(  # noqa: F821
        "RiderProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    agent_hub_staff: Mapped["AgentHubStaff"] = relationship(  # noqa: F821
        "AgentHubStaff",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    customer_orders: Mapped[list["Order"]] = relationship(  # noqa: F821
        "Order",
        back_populates="customer",
        foreign_keys="Order.customer_id",
    )
    notifications: Mapped[list["Notification"]] = relationship(  # noqa: F821
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )
    sent_messages: Mapped[list["Message"]] = relationship(  # noqa: F821
        "Message",
        back_populates="sender",
        foreign_keys="Message.sender_id",
    )
    received_messages: Mapped[list["Message"]] = relationship(  # noqa: F821
        "Message",
        back_populates="receiver",
        foreign_keys="Message.receiver_id",
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def roles(self) -> list[str]:
        """All roles this user has — primary role first, then extra roles."""
        result = [self.role.value]
        for r in (self.extra_roles or []):
            if r not in result:
                result.append(r)
        return result

    def __repr__(self) -> str:
        return f"<User {self.email} [{self.role.value}]>"
