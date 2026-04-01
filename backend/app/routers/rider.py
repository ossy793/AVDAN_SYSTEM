"""
Rider routes — order picking, location updates, delivery confirmation.
All routes require JWT with role=RIDER.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import CurrentUser, require_role
from app.database import get_db
from app.models.order import OrderStatus
from app.models.rider import RiderProfile
from app.models.user import UserRole
from app.schemas.order import OrderOut, OrderSummary
from app.schemas.payment import PayoutRequest, PayoutResponse
from app.schemas.user import RiderLocationUpdate, RiderProfileOut, RiderProfileUpdate
from app.schemas.wallet import WalletOut, WalletTransactionList, WalletTransactionOut
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService
from app.services.rider_service import RiderService
from app.services.wallet_service import WalletService
from app.utils.helpers import paginate_response

router = APIRouter(dependencies=[Depends(require_role(UserRole.RIDER))])


# ── Profile ───────────────────────────────────────────────────────────────────
@router.get("/profile", response_model=RiderProfileOut)
async def get_rider_profile(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(RiderProfile).where(RiderProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Rider profile not set up yet.")
    return RiderProfileOut.model_validate(profile)


@router.patch("/profile", response_model=RiderProfileOut)
async def update_rider_profile(
    data: RiderProfileUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(RiderProfile).where(RiderProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Rider profile not found.")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(profile, field, value)
    await db.commit()
    await db.refresh(profile)
    return RiderProfileOut.model_validate(profile)


# ── Availability & Location ───────────────────────────────────────────────────
@router.post("/online", summary="Set rider status to online/available")
async def go_online(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = RiderService(db)
    profile = await svc.set_availability(current_user.id, True)
    return {"status": "online", "rider_id": str(profile.id)}


@router.post("/offline", summary="Set rider status to offline")
async def go_offline(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = RiderService(db)
    profile = await svc.set_availability(current_user.id, False)
    return {"status": "offline", "rider_id": str(profile.id)}


@router.post("/location", summary="Update real-time GPS location")
async def update_location(
    data: RiderLocationUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = RiderService(db)
    profile = await svc.update_location(current_user.id, data.latitude, data.longitude)
    return {
        "latitude": float(profile.current_latitude),
        "longitude": float(profile.current_longitude),
        "updated_at": profile.location_updated_at,
    }


# ── Orders ────────────────────────────────────────────────────────────────────
@router.get("/orders", summary="View assigned orders")
async def rider_orders(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
):
    rider_res = await db.execute(
        select(RiderProfile).where(RiderProfile.user_id == current_user.id)
    )
    rider = rider_res.scalar_one_or_none()
    if not rider:
        return paginate_response([], 0, page, per_page)

    svc = OrderService(db)
    orders, total = await svc.get_rider_orders(rider.id, page, per_page)
    return paginate_response(
        [OrderSummary.model_validate(o) for o in orders], total, page, per_page
    )


@router.get("/orders/active", summary="Get current active delivery assignment")
async def active_order(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = RiderService(db)
    order = await svc.get_current_assignment(current_user.id)
    if not order:
        return {"active_order": None}
    return {"active_order": OrderOut.model_validate(order)}


@router.get("/orders/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    rider_res = await db.execute(
        select(RiderProfile).where(RiderProfile.user_id == current_user.id)
    )
    rider = rider_res.scalar_one_or_none()
    svc = OrderService(db)
    order = await svc.get_order(order_id)
    if rider and order.rider_id != rider.id:
        raise HTTPException(status_code=403, detail="Not your order.")
    return OrderOut.model_validate(order)


@router.post("/orders/{order_id}/pickup", response_model=OrderOut,
             summary="Confirm pickup from vendor")
async def confirm_pickup(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = OrderService(db)
    order = await svc.transition(order_id, OrderStatus.PICKED_UP, current_user)
    return OrderOut.model_validate(order)


@router.post("/orders/{order_id}/arrived-hub", response_model=OrderOut,
             summary="Mark order arrived at agent hub")
async def arrived_at_hub(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = OrderService(db)
    order = await svc.transition(order_id, OrderStatus.AT_HUB, current_user)
    return OrderOut.model_validate(order)


@router.post("/orders/{order_id}/in-transit", response_model=OrderOut,
             summary="Mark order in transit to customer")
async def mark_in_transit(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = OrderService(db)
    order = await svc.transition(order_id, OrderStatus.IN_TRANSIT, current_user)
    return OrderOut.model_validate(order)


@router.post("/orders/{order_id}/deliver", response_model=OrderOut,
             summary="Confirm delivery and trigger escrow release")
async def confirm_delivery(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = OrderService(db)
    order = await svc.confirm_delivery(order_id, current_user)

    # Mark rider available again
    rider_svc = RiderService(db)
    await rider_svc.set_availability(current_user.id, True)

    return OrderOut.model_validate(order)


# ── Wallet & Payout ───────────────────────────────────────────────────────────
@router.get("/wallet", response_model=WalletOut)
async def get_wallet(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = WalletService(db)
    wallet = await svc.get_wallet(current_user.id)
    return WalletOut.model_validate(wallet)


@router.post("/payout", response_model=PayoutResponse)
async def request_payout(
    data: PayoutRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    rider_res = await db.execute(
        select(RiderProfile).where(RiderProfile.user_id == current_user.id)
    )
    rider = rider_res.scalar_one_or_none()
    if not rider or not rider.bank_account_number or not rider.bank_code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Bank details not set up. Update your rider profile first.",
        )
    svc = PaymentService(db)
    try:
        result = await svc.request_payout(
            user_id=current_user.id,
            amount=data.amount,
            account_number=rider.bank_account_number,
            bank_code=rider.bank_code,
            account_name=rider.bank_name or "",
            reason=data.reason or "Rider delivery earnings",
        )
    finally:
        await svc.aclose()
    return PayoutResponse(
        reference=result.get("reference", result.get("transactionReference", "")),
        amount=data.amount,
        status=result.get("status", "pending"),
        message="Payout initiated.",
    )
