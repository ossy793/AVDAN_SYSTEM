"""
Wallet & transaction management.
All monetary operations on wallet go through this service to ensure
atomicity and proper audit trails.
"""
import logging
import time
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InsufficientBalance, NotFound
from app.models.wallet import TransactionStatus, TransactionType, Wallet, WalletTransaction

logger = logging.getLogger(__name__)


def _ref() -> str:
    """Generate a unique wallet transaction reference."""
    return f"WTX-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8].upper()}"


class WalletService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_wallet(self, user_id: uuid.UUID) -> Wallet:
        wallet = Wallet(user_id=user_id, balance=0.00, ledger_balance=0.00)
        self.db.add(wallet)
        await self.db.flush()
        return wallet

    async def get_wallet(self, user_id: uuid.UUID) -> Wallet:
        result = await self.db.execute(
            select(Wallet).where(Wallet.user_id == user_id)
        )
        wallet = result.scalar_one_or_none()
        if not wallet:
            raise NotFound("Wallet")
        return wallet

    async def credit(
        self,
        user_id: uuid.UUID,
        amount: float,
        description: str,
        order_id: uuid.UUID | None = None,
        reference: str | None = None,
    ) -> WalletTransaction:
        wallet = await self.get_wallet(user_id)
        balance_before = float(wallet.balance)
        wallet.balance = round(balance_before + amount, 2)
        wallet.ledger_balance = round(float(wallet.ledger_balance) + amount, 2)

        tx = WalletTransaction(
            wallet_id=wallet.id,
            reference=reference or _ref(),
            transaction_type=TransactionType.CREDIT,
            amount=amount,
            balance_before=balance_before,
            balance_after=wallet.balance,
            description=description,
            status=TransactionStatus.COMPLETED,
            order_id=order_id,
        )
        self.db.add(tx)
        logger.info("Wallet credit: user=%s amount=₦%.2f", user_id, amount)
        return tx

    async def debit(
        self,
        user_id: uuid.UUID,
        amount: float,
        description: str,
        order_id: uuid.UUID | None = None,
        reference: str | None = None,
    ) -> WalletTransaction:
        wallet = await self.get_wallet(user_id)
        if float(wallet.balance) < amount:
            raise InsufficientBalance()

        balance_before = float(wallet.balance)
        wallet.balance = round(balance_before - amount, 2)
        wallet.ledger_balance = round(float(wallet.ledger_balance) - amount, 2)

        tx = WalletTransaction(
            wallet_id=wallet.id,
            reference=reference or _ref(),
            transaction_type=TransactionType.DEBIT,
            amount=amount,
            balance_before=balance_before,
            balance_after=wallet.balance,
            description=description,
            status=TransactionStatus.COMPLETED,
            order_id=order_id,
        )
        self.db.add(tx)
        logger.info("Wallet debit: user=%s amount=₦%.2f", user_id, amount)
        return tx

    async def get_transactions(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[WalletTransaction], int]:
        wallet = await self.get_wallet(user_id)

        count_result = await self.db.execute(
            select(func.count())
            .select_from(WalletTransaction)
            .where(WalletTransaction.wallet_id == wallet.id)
        )
        total = count_result.scalar_one()

        offset = (page - 1) * per_page
        result = await self.db.execute(
            select(WalletTransaction)
            .where(WalletTransaction.wallet_id == wallet.id)
            .order_by(WalletTransaction.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        return result.scalars().all(), total
