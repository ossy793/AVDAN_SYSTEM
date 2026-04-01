"""
Customer-facing routes.
All routes require JWT with role=CUSTOMER.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import CurrentUser, require_role
from app.database import get_db
from app.models.notification import Message
from app.models.order import OrderStatus
from app.models.product import Product, ProductCategory
from app.models.user import UserRole
from app.schemas.notification import MessageCreate, MessageOut, NotificationOut
from app.schemas.order import (
    OrderCancelRequest,
    OrderCreate,
    OrderDisputeRequest,
    OrderOut,
    OrderPaymentInit,
    OrderSummary,
    OrderTrackingOut,
)
from app.schemas.product import ProductListOut, ProductOut
from app.schemas.wallet import WalletOut, WalletTransactionList, WalletTransactionOut
from app.services.notification_service import NotificationService
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService
from app.services.wallet_service import WalletService
from app.utils.helpers import paginate_response

router = APIRouter(dependencies=[Depends(require_role(UserRole.CUSTOMER))])


# ── Products ──────────────────────────────────────────────────────────────────
@router.get("/products", summary="Browse available products")
async def list_products(
    db: Annotated[AsyncSession, Depends(get_db)],
    category: ProductCategory | None = None,
    search: str | None = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    query = select(Product).where(
        Product.is_available == True,
        Product.stock_quantity > 0,
    )
    if category:
        query = query.where(Product.category == category)
    if search:
        term = f"%{search}%"
        query = query.where(
            or_(Product.name.ilike(term), Product.description.ilike(term))
        )

    count = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count.scalar_one()

    result = await db.execute(
        query.order_by(Product.name).offset((page - 1) * per_page).limit(per_page)
    )
    products = result.scalars().all()
    return paginate_response(
        [ProductListOut.model_validate(p) for p in products], total, page, per_page
    )


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    return ProductOut.model_validate(product)


# ── Orders ────────────────────────────────────────────────────────────────────
@router.post(
    "/orders",
    response_model=OrderPaymentInit,
    status_code=status.HTTP_201_CREATED,
    summary="Place an order and initialise payment",
)
async def place_order(
    data: OrderCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    order_svc = OrderService(db)
    order = await order_svc.create_order(current_user, data)

    payment_svc = PaymentService(db)
    pay_data = await payment_svc.initialise_payment(order)
    await payment_svc.aclose()

    return OrderPaymentInit(
        order_id=order.id,
        order_reference=order.reference,
        payment_reference=pay_data["payment_reference"],
        checkout_url=pay_data["checkout_url"],
        transaction_reference=pay_data["transaction_reference"],
        amount=float(order.total_amount),
    )


@router.get("/orders", summary="List my orders")
async def my_orders(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
):
    svc = OrderService(db)
    orders, total = await svc.get_customer_orders(current_user.id, page, per_page)
    return paginate_response(
        [OrderSummary.model_validate(o) for o in orders], total, page, per_page
    )


@router.get("/orders/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = OrderService(db)
    order = await svc.get_order(order_id)
    if order.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your order.")
    return OrderOut.model_validate(order)


@router.get(
    "/orders/{order_id}/track",
    response_model=OrderTrackingOut,
    summary="Lightweight polling endpoint — returns stage timestamps for the tracking UI",
)
async def track_order(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = OrderService(db)
    order = await svc.get_order(order_id)
    if order.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your order.")
    return OrderTrackingOut.model_validate(order)


@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(
    order_id: uuid.UUID,
    body: OrderCancelRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = OrderService(db)
    order = await svc.cancel_order(order_id, current_user, body.reason)
    return OrderOut.model_validate(order)


@router.post("/orders/{order_id}/dispute", response_model=OrderOut)
async def dispute_order(
    order_id: uuid.UUID,
    body: OrderDisputeRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = OrderService(db)
    order = await svc.transition(order_id, OrderStatus.DISPUTED, current_user, body.reason)
    return OrderOut.model_validate(order)


# ── Wallet ────────────────────────────────────────────────────────────────────
@router.get("/wallet", response_model=WalletOut)
async def get_wallet(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = WalletService(db)
    wallet = await svc.get_wallet(current_user.id)
    return WalletOut.model_validate(wallet)


@router.get("/wallet/transactions", response_model=WalletTransactionList)
async def wallet_transactions(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
):
    svc = WalletService(db)
    txs, total = await svc.get_transactions(current_user.id, page, per_page)
    return WalletTransactionList(
        transactions=[WalletTransactionOut.model_validate(t) for t in txs],
        total=total,
        page=page,
        per_page=per_page,
    )


# ── Notifications ─────────────────────────────────────────────────────────────
@router.get("/notifications", response_model=list[NotificationOut])
async def my_notifications(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = NotificationService(db)
    notifs = await svc.get_unread(current_user.id)
    return [NotificationOut.model_validate(n) for n in notifs]


@router.post("/notifications/read-all")
async def mark_notifications_read(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = NotificationService(db)
    count = await svc.mark_all_read(current_user.id)
    return {"marked_read": count}


# ── Messages ──────────────────────────────────────────────────────────────────
@router.post("/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def send_message(
    data: MessageCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    msg = Message(
        order_id=data.order_id,
        sender_id=current_user.id,
        receiver_id=data.receiver_id,
        content=data.content,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return MessageOut.model_validate(msg)


@router.get("/messages/{order_id}", response_model=list[MessageOut])
async def get_order_messages(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Message)
        .where(Message.order_id == order_id)
        .order_by(Message.created_at.asc())
    )
    return [MessageOut.model_validate(m) for m in result.scalars().all()]
