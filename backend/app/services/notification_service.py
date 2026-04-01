"""
Notification service.
Persists in-app notifications and provides abstract hooks for SMS/WhatsApp.
All external notification calls are fire-and-forget (non-blocking).
"""
import logging
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationType
from app.models.order import Order, OrderStatus
from app.models.user import User

logger = logging.getLogger(__name__)

# Mapping from order status → notification type + messages
STATUS_NOTIFICATIONS: dict[OrderStatus, tuple[NotificationType, str, str]] = {
    OrderStatus.PAID: (
        NotificationType.PAYMENT_RECEIVED,
        "Payment Confirmed",
        "Your payment has been received. Your order is being sent to the vendor.",
    ),
    OrderStatus.VENDOR_CONFIRMED: (
        NotificationType.ORDER_CONFIRMED,
        "Order Accepted",
        "The vendor has accepted your order and will start preparing it.",
    ),
    OrderStatus.READY_FOR_PICKUP: (
        NotificationType.ORDER_READY,
        "Order Ready",
        "Your order is packed and a rider will pick it up shortly.",
    ),
    OrderStatus.RIDER_ASSIGNED: (
        NotificationType.RIDER_ASSIGNED,
        "Rider Assigned",
        "A rider has been assigned to your order.",
    ),
    OrderStatus.PICKED_UP: (
        NotificationType.ORDER_PICKED_UP,
        "Order Picked Up",
        "Your order has been picked up by the rider.",
    ),
    OrderStatus.AT_HUB: (
        NotificationType.ORDER_AT_HUB,
        "At Agent Hub",
        "Your order has arrived at the agent hub for verification.",
    ),
    OrderStatus.IN_TRANSIT: (
        NotificationType.ORDER_IN_TRANSIT,
        "Out for Delivery",
        "Your order is on the way! Track your rider on the map.",
    ),
    OrderStatus.DELIVERED: (
        NotificationType.ORDER_DELIVERED,
        "Order Delivered",
        "Your order has been delivered. Thank you for using ADVAN!",
    ),
    OrderStatus.CANCELLED: (
        NotificationType.ORDER_CANCELLED,
        "Order Cancelled",
        "Your order has been cancelled.",
    ),
}


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        user_id: uuid.UUID,
        notification_type: NotificationType,
        title: str,
        message: str,
        order_id: uuid.UUID | None = None,
    ) -> Notification:
        notif = Notification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            order_id=order_id,
        )
        self.db.add(notif)
        # Flush but let the caller commit
        await self.db.flush()
        logger.debug("Notification created: %s → user=%s", notification_type.value, user_id)
        return notif

    async def notify_new_order(self, order: Order) -> None:
        """Notify vendor when a new paid order arrives."""
        if not order.vendor_id:
            return
        vendor_res = await self.db.execute(
            select(User)
            .join(User.vendor_profile)
            .where(User.vendor_profile.has(id=order.vendor_id))
        )
        vendor_user = vendor_res.scalar_one_or_none()
        if vendor_user:
            await self.create(
                user_id=vendor_user.id,
                notification_type=NotificationType.ORDER_PLACED,
                title="New Order Received",
                message=(
                    f"You have a new order #{order.reference} worth ₦{order.subtotal:,.2f}. "
                    "Please accept it promptly."
                ),
                order_id=order.id,
            )
        # Abstract hooks for external channels
        await self._sms_hook(order.customer.phone, f"ADVAN: Order {order.reference} placed.")
        await self._db_commit_safe()

    async def notify_status_change(self, order: Order, new_status: OrderStatus) -> None:
        entry = STATUS_NOTIFICATIONS.get(new_status)
        if not entry:
            return
        notif_type, title, message = entry

        # Always notify the customer
        await self.create(
            user_id=order.customer_id,
            notification_type=notif_type,
            title=title,
            message=message,
            order_id=order.id,
        )
        await self._db_commit_safe()

    async def get_unread(self, user_id: uuid.UUID) -> list[Notification]:
        result = await self.db.execute(
            select(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
            .order_by(Notification.created_at.desc())
        )
        return result.scalars().all()

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        result = await self.db.execute(
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True)
            .returning(Notification.id)
        )
        updated = result.fetchall()
        await self.db.commit()
        return len(updated)

    # ── Abstract external notification hooks ──────────────────────────────
    async def _sms_hook(self, phone: str, message: str) -> None:
        """
        Override this with your actual SMS provider (Termii, Twilio, etc.).
        Currently a no-op stub.
        """
        logger.debug("SMS stub → %s: %s", phone, message)

    async def _whatsapp_hook(self, phone: str, message: str) -> None:
        """Override with WhatsApp Business API integration."""
        logger.debug("WhatsApp stub → %s: %s", phone, message)

    async def _db_commit_safe(self) -> None:
        try:
            await self.db.commit()
        except Exception as e:
            logger.warning("Notification commit failed: %s", e)
            await self.db.rollback()
