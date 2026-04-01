"""
Monnify payment integration.
Handles: payment initialisation, webhook verification, escrow release, payouts.

DEMO_MODE=true  →  all Monnify API calls are skipped; payments auto-confirm instantly.
                   Safe for investor demos — no real keys required.

Monnify API docs: https://developers.monnify.com
"""
import base64
import json
import logging
import time
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import (
    EscrowReleaseError,
    NotFound,
    PaymentFailed,
    WebhookVerificationFailed,
)
from app.core.security import verify_monnify_signature
from app.models.order import Order, OrderStatus
from app.models.payment import Escrow, EscrowStatus, Payment, PaymentStatus
from app.models.rider import RiderProfile
from app.models.vendor import VendorProfile
from app.services.notification_service import NotificationService
from app.services.wallet_service import WalletService

logger = logging.getLogger(__name__)


def _monnify_ref() -> str:
    return f"ADV-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8].upper()}"


class PaymentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._http = httpx.AsyncClient(
            base_url=settings.MONNIFY_BASE_URL,
            timeout=30.0,
        )
        self._token: str | None = None

    async def __aenter__(self) -> "PaymentService":
        return self

    async def __aexit__(self, *_) -> None:
        await self.aclose()

    # ── Monnify authentication ────────────────────────────────────────────
    async def _get_access_token(self) -> str:
        """
        Obtain a Monnify OAuth2 access token using Basic Auth.
        The token is cached on this instance for the lifetime of the request.
        """
        if self._token:
            return self._token

        credentials = base64.b64encode(
            f"{settings.MONNIFY_API_KEY}:{settings.MONNIFY_SECRET_KEY}".encode()
        ).decode()

        response = await self._http.post(
            "/api/v1/auth/login",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json",
            },
        )
        data = response.json()
        if not data.get("requestSuccessful"):
            logger.error("Monnify auth failed: %s", data)
            raise PaymentFailed("Failed to authenticate with Monnify.")

        self._token = data["responseBody"]["accessToken"]
        return self._token

    async def _auth_headers(self) -> dict[str, str]:
        token = await self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    # ── Initialise payment ────────────────────────────────────────────────
    async def initialise_payment(self, order: Order) -> dict:
        """
        Create a Monnify checkout link for the given order.
        In DEMO_MODE, skips Monnify entirely and auto-confirms the payment.
        Returns checkout_url, payment_reference, transaction_reference.
        """
        reference = _monnify_ref()

        payment = Payment(
            order_id=order.id,
            reference=reference,
            amount=float(order.total_amount),
            currency="NGN",
            status=PaymentStatus.PENDING,
        )
        self.db.add(payment)
        await self.db.commit()

        # ── DEMO MODE ─────────────────────────────────────────────────────
        if settings.DEMO_MODE:
            logger.info("DEMO MODE: auto-confirming payment for order %s", order.reference)
            await self._demo_confirm(payment, order)
            return {
                "checkout_url": (
                    f"http://127.0.0.1:8000/api/payment/demo/confirmed?ref={reference}"
                ),
                "payment_reference": reference,
                "transaction_reference": f"demo_{reference}",
            }

        # ── LIVE MODE ─────────────────────────────────────────────────────
        headers = await self._auth_headers()
        payload = {
            "amount": float(order.total_amount),
            "customerName": f"{order.customer.first_name} {order.customer.last_name}",
            "customerEmail": order.customer.email,
            "paymentReference": reference,
            "paymentDescription": f"ADVAN Order {order.reference}",
            "currencyCode": "NGN",
            "contractCode": settings.MONNIFY_CONTRACT_CODE,
            "redirectUrl": settings.MONNIFY_REDIRECT_URL,
            "paymentMethods": ["CARD", "ACCOUNT_TRANSFER", "USSD", "PHONE_NUMBER"],
        }

        response = await self._http.post(
            "/api/v1/merchant/transactions/init-transaction",
            json=payload,
            headers=headers,
        )
        data = response.json()

        if not data.get("requestSuccessful"):
            logger.error("Monnify init failed: %s", data)
            raise PaymentFailed(
                data.get("responseMessage", "Payment initialisation failed.")
            )

        body = data["responseBody"]
        return {
            "checkout_url": body["checkoutUrl"],
            "payment_reference": reference,
            "transaction_reference": body.get("transactionReference", ""),
        }

    async def _demo_confirm(self, payment: Payment, order: Order) -> None:
        """Instantly confirm a payment without any Monnify call (DEMO_MODE only)."""
        payment.status = PaymentStatus.PAID
        payment.paystack_transaction_id = f"demo_{payment.reference}"
        payment.channel = "demo"
        payment.paid_at = datetime.now(tz=timezone.utc)

        if order.status == OrderStatus.PENDING:
            order.status = OrderStatus.PAID

        escrow = Escrow(
            payment_id=payment.id,
            order_id=payment.order_id,
            total_held=payment.amount,
            status=EscrowStatus.HELD,
        )
        self.db.add(escrow)
        await self.db.commit()

        notif_svc = NotificationService(self.db)
        await notif_svc.notify_new_order(order)
        logger.info("DEMO MODE: payment %s confirmed, escrow created", payment.reference)

    # ── Verify payment ────────────────────────────────────────────────────
    async def verify_and_confirm(self, reference: str) -> Payment:
        """
        Verify a payment with Monnify and confirm it in the database.
        Idempotent — safe to call multiple times for the same reference.
        """
        result = await self.db.execute(
            select(Payment).where(Payment.reference == reference)
        )
        payment: Payment | None = result.scalar_one_or_none()
        if not payment:
            raise NotFound("Payment")

        if payment.status == PaymentStatus.PAID:
            return payment  # already confirmed — idempotent

        if settings.DEMO_MODE:
            order_result = await self.db.execute(
                select(Order).where(Order.id == payment.order_id)
            )
            order = order_result.scalar_one_or_none()
            if order:
                await self._demo_confirm(payment, order)
            return payment

        # ── LIVE MODE ─────────────────────────────────────────────────────
        headers = await self._auth_headers()
        response = await self._http.get(
            "/api/v2/merchant/transactions/query",
            params={"paymentReference": reference},
            headers=headers,
        )
        data = response.json()

        if not data.get("requestSuccessful"):
            raise PaymentFailed("Payment verification failed.")

        tx = data["responseBody"]
        is_paid = tx.get("paymentStatus") == "PAID"

        if is_paid:
            payment.status = PaymentStatus.PAID
            payment.paystack_transaction_id = tx.get("transactionReference", "")
            payment.channel = tx.get("paymentMethod", "")
            payment.paid_at = datetime.now(tz=timezone.utc)

            order_result = await self.db.execute(
                select(Order).where(Order.id == payment.order_id)
            )
            order: Order | None = order_result.scalar_one_or_none()
            if order and order.status == OrderStatus.PENDING:
                order.status = OrderStatus.PAID

            escrow = Escrow(
                payment_id=payment.id,
                order_id=payment.order_id,
                total_held=payment.amount,
                status=EscrowStatus.HELD,
            )
            self.db.add(escrow)
            await self.db.commit()
            await self.db.refresh(payment)

            if order:
                notif_svc = NotificationService(self.db)
                await notif_svc.notify_new_order(order)

            logger.info(
                "Payment confirmed: ref=%s order=%s", reference, payment.order_id
            )
        else:
            payment.status = PaymentStatus.FAILED
            await self.db.commit()

        return payment

    # ── Process Monnify webhook ───────────────────────────────────────────
    async def handle_webhook(self, raw_body: bytes, signature: str) -> None:
        """
        Verify HMAC-SHA512 signature and dispatch the Monnify event.
        Silently ignored in DEMO_MODE.
        """
        if settings.DEMO_MODE:
            return

        if not verify_monnify_signature(raw_body, signature):
            raise WebhookVerificationFailed()

        event_data = json.loads(raw_body)
        event_type = event_data.get("eventType", "")

        logger.info("Monnify webhook: %s", event_type)

        if event_type == "SUCCESSFUL_TRANSACTION":
            ref = event_data.get("eventData", {}).get("paymentReference", "")
            if ref:
                await self.verify_and_confirm(ref)
        elif event_type in ("FAILED_TRANSACTION", "REVERSED_TRANSACTION"):
            ref = event_data.get("eventData", {}).get("paymentReference", "")
            if ref:
                await self._handle_failed_payment(ref)
        elif event_type == "SUCCESSFUL_DISBURSEMENT":
            await self._handle_disbursement_success(event_data.get("eventData", {}))
        elif event_type == "FAILED_DISBURSEMENT":
            await self._handle_disbursement_failed(event_data.get("eventData", {}))

    # ── Release escrow after delivery ─────────────────────────────────────
    async def release_escrow(self, order: Order) -> Escrow:
        """
        Split held funds: vendor (subtotal) + rider (delivery_fee) + hub (hub_fee).
        Platform fee is retained. Works identically in DEMO_MODE and LIVE.
        """
        escrow_result = await self.db.execute(
            select(Escrow).where(
                Escrow.order_id == order.id,
                Escrow.status == EscrowStatus.HELD,
            )
        )
        escrow: Escrow | None = escrow_result.scalar_one_or_none()
        if not escrow:
            raise EscrowReleaseError("No held escrow found for this order.")

        subtotal = float(order.subtotal)
        delivery_fee = float(order.delivery_fee)
        hub_fee = float(order.hub_fee)
        platform_fee = float(order.platform_fee)

        wallet_svc = WalletService(self.db)

        # Credit vendor wallet
        if order.vendor_id:
            vendor_res = await self.db.execute(
                select(VendorProfile).where(VendorProfile.id == order.vendor_id)
            )
            vendor = vendor_res.scalar_one_or_none()
            if vendor:
                await wallet_svc.credit(
                    user_id=vendor.user_id,
                    amount=subtotal,
                    description=f"Earnings from order {order.reference}",
                    order_id=order.id,
                    reference=f"ESC-V-{order.reference}",
                )

        # Credit rider wallet
        if order.rider_id:
            rider_res = await self.db.execute(
                select(RiderProfile).where(RiderProfile.id == order.rider_id)
            )
            rider = rider_res.scalar_one_or_none()
            if rider:
                await wallet_svc.credit(
                    user_id=rider.user_id,
                    amount=delivery_fee,
                    description=f"Delivery earnings for order {order.reference}",
                    order_id=order.id,
                    reference=f"ESC-R-{order.reference}",
                )

        escrow.vendor_amount = subtotal
        escrow.rider_amount = delivery_fee
        escrow.hub_amount = hub_fee
        escrow.platform_amount = platform_fee
        escrow.status = EscrowStatus.RELEASED
        escrow.released_at = datetime.now(tz=timezone.utc)

        await self.db.commit()
        await self.db.refresh(escrow)
        logger.info("Escrow released for order %s", order.reference)
        return escrow

    # ── Payout via Monnify disbursement ───────────────────────────────────
    async def request_payout(
        self,
        user_id: uuid.UUID,
        amount: float,
        account_number: str,
        bank_code: str,
        account_name: str,
        reason: str = "Earnings withdrawal",
    ) -> dict:
        """
        Debit the user's ADVAN wallet and initiate a Monnify bank transfer.
        On transfer failure the wallet debit is reversed automatically.
        """
        wallet_svc = WalletService(self.db)
        transfer_ref = f"PAY-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8].upper()}"

        await wallet_svc.debit(
            user_id=user_id,
            amount=amount,
            description=f"Payout withdrawal: ₦{amount:,.2f}",
            reference=transfer_ref,
        )

        if settings.DEMO_MODE:
            await self.db.commit()
            return {"reference": f"DEMO_TRF_{transfer_ref}", "status": "SUCCESS"}

        headers = await self._auth_headers()
        payload = {
            "amount": amount,
            "reference": transfer_ref,
            "narration": reason,
            "destinationBankCode": bank_code,
            "destinationAccountNumber": account_number,
            "destinationAccountName": account_name,
            "currency": "NGN",
            "sourceAccountNumber": settings.MONNIFY_WALLET_ACCOUNT,
        }

        response = await self._http.post(
            "/api/v1/disbursements/single",
            json=payload,
            headers=headers,
        )
        data = response.json()

        if not data.get("requestSuccessful"):
            # Reverse the wallet debit so the user's balance is restored
            await wallet_svc.credit(
                user_id=user_id,
                amount=amount,
                description="Payout reversal — transfer initiation failed",
                reference=f"REV-{transfer_ref}",
            )
            raise PaymentFailed(
                data.get("responseMessage", "Transfer initiation failed.")
            )

        await self.db.commit()
        return data["responseBody"]

    # ── Internal event handlers ───────────────────────────────────────────
    async def _handle_failed_payment(self, reference: str) -> None:
        result = await self.db.execute(
            select(Payment).where(Payment.reference == reference)
        )
        payment = result.scalar_one_or_none()
        if payment and payment.status == PaymentStatus.PENDING:
            payment.status = PaymentStatus.FAILED
            await self.db.commit()
            logger.warning("Payment failed/reversed: ref=%s", reference)

    async def _handle_disbursement_success(self, tx_data: dict) -> None:
        logger.info("Disbursement succeeded: ref=%s", tx_data.get("reference", ""))

    async def _handle_disbursement_failed(self, tx_data: dict) -> None:
        logger.warning("Disbursement failed: ref=%s", tx_data.get("reference", ""))

    async def aclose(self) -> None:
        await self._http.aclose()
