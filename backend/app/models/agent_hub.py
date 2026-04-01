import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class StaffRole(str, enum.Enum):
    MANAGER = "manager"
    STAFF = "staff"


class AgentHub(Base):
    """
    Physical distribution / verification hub.
    Riders drop packages here; agents verify and re-dispatch to customers.
    """
    __tablename__ = "agent_hubs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    area: Mapped[str] = mapped_column(String(100), nullable=True)   # e.g. "Ikeja", "Lekki"
    state: Mapped[str] = mapped_column(String(50), default="Lagos", nullable=False)
    latitude: Mapped[float] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[float] = mapped_column(Numeric(10, 7), nullable=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    capacity: Mapped[int] = mapped_column(default=100, nullable=False)  # max daily packages

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────
    staff: Mapped[list["AgentHubStaff"]] = relationship(
        "AgentHubStaff",
        back_populates="hub",
        cascade="all, delete-orphan",
    )
    orders: Mapped[list["Order"]] = relationship(  # noqa: F821
        "Order",
        back_populates="agent_hub",
        foreign_keys="Order.agent_hub_id",
    )

    def __repr__(self) -> str:
        return f"<AgentHub {self.name} — {self.area}>"


class AgentHubStaff(Base):
    """
    Links a User (role=AGENT) to a specific AgentHub with a staff role.
    """
    __tablename__ = "agent_hub_staff"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False, index=True
    )
    hub_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_hubs.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    staff_role: Mapped[StaffRole] = mapped_column(
        SAEnum(StaffRole, values_callable=lambda x: [e.value for e in x]),
        nullable=False, default=StaffRole.STAFF
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="agent_hub_staff")  # noqa: F821
    hub: Mapped["AgentHub"] = relationship("AgentHub", back_populates="staff")

    def __repr__(self) -> str:
        return f"<AgentHubStaff {self.user_id} @ {self.hub_id}>"
