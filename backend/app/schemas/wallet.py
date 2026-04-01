import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.wallet import TransactionType, TransactionStatus


class WalletOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID
    balance: float
    ledger_balance: float
    currency: str
    updated_at: datetime


class WalletTransactionOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    reference: str
    transaction_type: TransactionType
    amount: float
    balance_before: float
    balance_after: float
    description: str | None
    status: TransactionStatus
    order_id: uuid.UUID | None
    created_at: datetime


class WalletTransactionList(BaseModel):
    transactions: list[WalletTransactionOut]
    total: int
    page: int
    per_page: int
