import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TransactionType(str, enum.Enum):
    CREDIT = "credit"
    DEBIT = "debit"


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERSED = "reversed"


class Wallet(Base):
    """
    Every user gets exactly one wallet on registration.
    Vendors and riders accumulate earnings here before requesting a payout.
    """
    __tablename__ = "wallets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False, index=True
    )
    balance: Mapped[float] = mapped_column(
        Numeric(14, 2), nullable=False, default=0.00
    )
    ledger_balance: Mapped[float] = mapped_column(
        Numeric(14, 2), nullable=False, default=0.00
    )   # includes pending credits
    currency: Mapped[str] = mapped_column(String(5), default="NGN", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="wallet")  # noqa: F821
    transactions: Mapped[list["WalletTransaction"]] = relationship(
        "WalletTransaction",
        back_populates="wallet",
        cascade="all, delete-orphan",
        order_by="WalletTransaction.created_at.desc()",
    )

    def __repr__(self) -> str:
        return f"<Wallet user={self.user_id} ₦{self.balance}>"


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallets.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    reference: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    transaction_type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    balance_before: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[TransactionStatus] = mapped_column(
        SAEnum(TransactionStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False, default=TransactionStatus.COMPLETED
    )
    # Optional link to order that triggered this transaction
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True
    )
    # Paystack transfer code (populated for payout debit transactions)
    paystack_transfer_code: Mapped[str] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # ── Relationships ─────────────────────────────────────────────────────
    wallet: Mapped["Wallet"] = relationship("Wallet", back_populates="transactions")

    def __repr__(self) -> str:
        return (
            f"<WalletTx {self.transaction_type.value} ₦{self.amount} ref={self.reference}>"
        )
