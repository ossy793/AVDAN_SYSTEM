import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ProductCategory(str, enum.Enum):
    FOOD = "food"
    GROCERIES = "groceries"
    ELECTRONICS = "electronics"
    FASHION = "fashion"
    HEALTH = "health"
    HOME = "home"
    BOOKS = "books"
    SPORTS = "sports"
    BEAUTY = "beauty"
    OTHER = "other"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor_profiles.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    category: Mapped[ProductCategory] = mapped_column(
        SAEnum(ProductCategory, values_callable=lambda x: [e.value for e in x]),
        nullable=False, default=ProductCategory.OTHER, index=True
    )
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_url: Mapped[str] = mapped_column(String(500), nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Numeric(6, 3), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────
    vendor: Mapped["VendorProfile"] = relationship(  # noqa: F821
        "VendorProfile", back_populates="products"
    )
    order_items: Mapped[list["OrderItem"]] = relationship(  # noqa: F821
        "OrderItem", back_populates="product"
    )

    def __repr__(self) -> str:
        return f"<Product {self.name} — ₦{self.price}>"
