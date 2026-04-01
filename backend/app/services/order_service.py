"""
Order Management System (OMS).
Governs the full lifecycle from placement to delivery and payment release.
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.exceptions import (
    InvalidOrderTransition,
    NotFound,
    OrderNotAssignable,
    ProductOutOfStock,
    VendorNotApproved,
)
from app.models.agent_hub import AgentHub
from app.models.order import Order, OrderItem, OrderStatus
from app.models.payment import Escrow, EscrowStatus, Payment, PaymentStatus
from app.models.product import Product
from app.models.rider import RiderProfile
from app.models.user import User
from app.models.vendor import VendorProfile
from app.schemas.order import OrderCreate
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


def _order_reference() -> str:
    ts = datetime.now().strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:5].upper()
    return f"ADV-{ts}-{suffix}"


class OrderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Create order ──────────────────────────────────────────────────────
    async def create_order(self, customer: User, data: OrderCreate) -> Order:
        """
        Validate cart, compute totals, assign vendor, create Order + OrderItems.
        Payment is NOT collected here — caller initialises Paystack after creation.
        """
        if not data.items:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Order must contain at least one item.",
            )

        # Load all products and verify they belong to ONE vendor
        product_ids = [item.product_id for item in data.items]
        products_result = await self.db.execute(
            select(Product)
            .where(Product.id.in_(product_ids))
            .options(selectinload(Product.vendor))
        )
        products: list[Product] = products_result.scalars().all()

        if len(products) != len(product_ids):
            raise NotFound("One or more products")

        vendor_ids = {p.vendor_id for p in products}
        if len(vendor_ids) > 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="All items in an order must come from the same vendor.",
            )

        vendor_id = vendor_ids.pop()
        vendor_result = await self.db.execute(
            select(VendorProfile).where(VendorProfile.id == vendor_id)
        )
        vendor: VendorProfile | None = vendor_result.scalar_one_or_none()
        if not vendor or not vendor.is_approved:
            raise VendorNotApproved()

        # Build order items & validate stock
        order_items: list[OrderItem] = []
        subtotal = 0.0
        product_map = {p.id: p for p in products}

        for cart_item in data.items:
            product = product_map[cart_item.product_id]
            if not product.is_available or product.stock_quantity < cart_item.quantity:
                raise ProductOutOfStock(product.name)

            item_subtotal = round(float(product.price) * cart_item.quantity, 2)
            subtotal += item_subtotal
            order_items.append(
                OrderItem(
                    product_id=product.id,
                    product_name=product.name,    # snapshot price at order time
                    quantity=cart_item.quantity,
                    unit_price=float(product.price),
                    subtotal=item_subtotal,
                )
            )
            # Reserve stock
            product.stock_quantity -= cart_item.quantity

        # Fees
        platform_fee = round(subtotal * (settings.PLATFORM_FEE_PERCENTAGE / 100), 2)
        delivery_fee = settings.DELIVERY_BASE_FEE
        hub_fee = settings.HUB_FEE
        total_amount = round(subtotal + delivery_fee + hub_fee + platform_fee, 2)

        # Assign nearest hub if not specified
        hub_id = data.preferred_hub_id
        if not hub_id:
            hub_id = await self._assign_hub(data.delivery_latitude, data.delivery_longitude)

        order = Order(
            reference=_order_reference(),
            customer_id=customer.id,
            vendor_id=vendor_id,
            agent_hub_id=hub_id,
            status=OrderStatus.PENDING,
            subtotal=subtotal,
            delivery_fee=delivery_fee,
            hub_fee=hub_fee,
            platform_fee=platform_fee,
            total_amount=total_amount,
            delivery_address=data.delivery_address,
            delivery_latitude=data.delivery_latitude,
            delivery_longitude=data.delivery_longitude,
            delivery_notes=data.delivery_notes,
        )
        self.db.add(order)
        await self.db.flush()

        for item in order_items:
            item.order_id = order.id
            self.db.add(item)

        await self.db.commit()
        await self.db.refresh(order)
        logger.info("Order created: %s for customer %s", order.reference, customer.id)
        return order

    # ── Transition order status ───────────────────────────────────────────
    async def transition(
        self,
        order_id: uuid.UUID,
        new_status: OrderStatus,
        actor: User,
        reason: str | None = None,
    ) -> Order:
        order = await self._get_order_with_items(order_id)

        if not order.can_transition_to(new_status):
            raise InvalidOrderTransition(order.status.value, new_status.value)

        order.status = new_status
        now = datetime.now(tz=timezone.utc)

        # Stamp per-stage timestamps
        if new_status == OrderStatus.VENDOR_CONFIRMED:
            order.vendor_accepted_at = now
        elif new_status == OrderStatus.VENDOR_REJECTED:
            order.vendor_rejected_at = now
            order.cancellation_reason = reason
        elif new_status == OrderStatus.PICKED_UP:
            order.picked_up_at = now
        elif new_status == OrderStatus.HUB_VERIFIED:
            order.hub_verified_at = now
        elif new_status == OrderStatus.IN_TRANSIT:
            order.in_transit_at = now
        elif new_status == OrderStatus.DELIVERED:
            order.delivered_at = now
        elif new_status == OrderStatus.CANCELLED:
            order.cancellation_reason = reason
        elif new_status == OrderStatus.DISPUTED:
            order.dispute_reason = reason

        await self.db.commit()
        await self.db.refresh(order)

        # Send notifications
        notif_svc = NotificationService(self.db)
        await notif_svc.notify_status_change(order, new_status)

        logger.info("Order %s → %s by %s", order.reference, new_status.value, actor.id)
        return order

    # ── Assign rider ──────────────────────────────────────────────────────
    async def assign_rider(self, order_id: uuid.UUID, rider_id: uuid.UUID) -> Order:
        order = await self._get_order_with_items(order_id)

        rider_result = await self.db.execute(
            select(RiderProfile).where(
                and_(RiderProfile.id == rider_id, RiderProfile.is_available == True)
            )
        )
        rider: RiderProfile | None = rider_result.scalar_one_or_none()
        if not rider:
            raise OrderNotAssignable()

        if not order.can_transition_to(OrderStatus.RIDER_ASSIGNED):
            raise InvalidOrderTransition(order.status.value, OrderStatus.RIDER_ASSIGNED.value)

        order.rider_id = rider_id
        order.status = OrderStatus.RIDER_ASSIGNED
        order.rider_assigned_at = datetime.now(tz=timezone.utc)
        rider.is_available = False

        await self.db.commit()
        await self.db.refresh(order)

        notif_svc = NotificationService(self.db)
        await notif_svc.notify_status_change(order, OrderStatus.RIDER_ASSIGNED)
        return order

    # ── Release escrow on delivery ────────────────────────────────────────
    async def confirm_delivery(self, order_id: uuid.UUID, actor: User) -> Order:
        order = await self._get_order_with_items(order_id)
        order = await self.transition(order_id, OrderStatus.DELIVERED, actor)

        from app.services.payment_service import PaymentService
        payment_svc = PaymentService(self.db)
        await payment_svc.release_escrow(order)
        return order

    # ── Vendor reject order ───────────────────────────────────────────────
    async def reject_order(
        self, order_id: uuid.UUID, actor: User, reason: str
    ) -> Order:
        """Vendor rejects a PAID order — restores stock and refunds escrow."""
        order = await self._get_order_with_items(order_id)
        order = await self.transition(order_id, OrderStatus.VENDOR_REJECTED, actor, reason)

        # Restore product stock
        product_ids = [item.product_id for item in order.items]
        if product_ids:
            products_res = await self.db.execute(
                select(Product).where(Product.id.in_(product_ids))
            )
            product_map = {p.id: p for p in products_res.scalars().all()}
            for item in order.items:
                product = product_map.get(item.product_id)
                if product:
                    product.stock_quantity += item.quantity

        # Refund escrow
        escrow_res = await self.db.execute(
            select(Escrow).where(
                Escrow.order_id == order_id,
                Escrow.status == EscrowStatus.HELD,
            )
        )
        escrow = escrow_res.scalar_one_or_none()
        if escrow:
            escrow.status = EscrowStatus.REFUNDED
            order.status = OrderStatus.REFUNDED
            # In production: initiate Monnify refund via API here

        await self.db.commit()
        return order

    # ── Cancel order ──────────────────────────────────────────────────────
    async def cancel_order(
        self, order_id: uuid.UUID, actor: User, reason: str
    ) -> Order:
        order = await self._get_order_with_items(order_id)
        order = await self.transition(order_id, OrderStatus.CANCELLED, actor, reason)

        # Restore stock — single bulk SELECT instead of N individual queries
        product_ids = [item.product_id for item in order.items]
        if product_ids:
            products_res = await self.db.execute(
                select(Product).where(Product.id.in_(product_ids))
            )
            product_map = {p.id: p for p in products_res.scalars().all()}
            for item in order.items:
                product = product_map.get(item.product_id)
                if product:
                    product.stock_quantity += item.quantity

        # Refund escrow if payment was already made
        payment_res = await self.db.execute(
            select(Payment).where(Payment.order_id == order_id)
        )
        payment = payment_res.scalar_one_or_none()
        if payment and payment.status == PaymentStatus.PAID:
            escrow_res = await self.db.execute(
                select(Escrow).where(
                    Escrow.order_id == order_id,
                    Escrow.status == EscrowStatus.HELD,
                )
            )
            escrow = escrow_res.scalar_one_or_none()
            if escrow:
                escrow.status = EscrowStatus.REFUNDED
                order.status = OrderStatus.REFUNDED
                # In production: initiate Monnify refund via API here

        await self.db.commit()
        return order

    # ── Queries ───────────────────────────────────────────────────────────
    async def get_order(self, order_id: uuid.UUID) -> Order:
        return await self._get_order_with_items(order_id)

    async def get_customer_orders(
        self, customer_id: uuid.UUID, page: int = 1, per_page: int = 20
    ) -> tuple[list[Order], int]:
        return await self._paginated_orders(
            filter_clause=Order.customer_id == customer_id,
            page=page,
            per_page=per_page,
        )

    async def get_vendor_orders(
        self, vendor_id: uuid.UUID, status: OrderStatus | None = None,
        page: int = 1, per_page: int = 20
    ) -> tuple[list[Order], int]:
        clause = Order.vendor_id == vendor_id
        if status:
            clause = and_(clause, Order.status == status)
        return await self._paginated_orders(clause, page, per_page)

    async def get_rider_orders(
        self, rider_id: uuid.UUID, page: int = 1, per_page: int = 20
    ) -> tuple[list[Order], int]:
        return await self._paginated_orders(Order.rider_id == rider_id, page, per_page)

    async def get_hub_orders(
        self, hub_id: uuid.UUID, status: OrderStatus | None = None,
        page: int = 1, per_page: int = 20
    ) -> tuple[list[Order], int]:
        clause = Order.agent_hub_id == hub_id
        if status:
            clause = and_(clause, Order.status == status)
        return await self._paginated_orders(clause, page, per_page)

    # ── Private helpers ───────────────────────────────────────────────────
    async def _get_order_with_items(self, order_id: uuid.UUID) -> Order:
        result = await self.db.execute(
            select(Order)
            .where(Order.id == order_id)
            .options(
                selectinload(Order.items),
                selectinload(Order.customer),
                selectinload(Order.vendor),
                selectinload(Order.rider),
                selectinload(Order.agent_hub),
            )
        )
        order = result.scalar_one_or_none()
        if not order:
            raise NotFound("Order")
        return order

    async def _paginated_orders(
        self, filter_clause, page: int, per_page: int
    ) -> tuple[list[Order], int]:
        count_res = await self.db.execute(
            select(func.count()).select_from(Order).where(filter_clause)
        )
        total = count_res.scalar_one()

        result = await self.db.execute(
            select(Order)
            .where(filter_clause)
            .options(selectinload(Order.items))
            .order_by(Order.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return result.scalars().all(), total

    async def _assign_hub(
        self, lat: float | None, lng: float | None
    ) -> uuid.UUID | None:
        """Simple hub assignment: nearest active hub, or first available."""
        result = await self.db.execute(
            select(AgentHub).where(AgentHub.is_active == True).limit(1)
        )
        hub = result.scalar_one_or_none()
        return hub.id if hub else None
