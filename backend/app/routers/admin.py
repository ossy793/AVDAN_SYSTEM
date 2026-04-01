"""
Admin dashboard routes — full platform visibility and management.
All routes require JWT with role=ADMIN.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import CurrentUser, require_role
from app.database import get_db
from app.models.agent_hub import AgentHub, AgentHubStaff
from app.models.order import Order, OrderStatus
from app.models.payment import Escrow, Payment, PaymentStatus
from app.models.rider import RiderProfile
from app.models.user import User, UserRole
from app.models.vendor import VendorProfile
from app.models.wallet import Wallet
from app.services.order_service import OrderService
from app.schemas.user import AgentHubCreate, AgentHubOut, UserPublic, VendorProfileOut, RiderProfileOut
from app.schemas.order import OrderOut, OrderSummary
from app.schemas.payment import EscrowOut, PaymentOut
from app.utils.helpers import paginate_response

router = APIRouter(dependencies=[Depends(require_role(UserRole.ADMIN))])


# ── Platform analytics ────────────────────────────────────────────────────────
@router.get("/analytics", summary="High-level platform metrics")
async def platform_analytics(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    total_users = (await db.execute(select(func.count(User.id)))).scalar_one()
    total_orders = (await db.execute(select(func.count(Order.id)))).scalar_one()
    total_vendors = (
        await db.execute(select(func.count(VendorProfile.id)))
    ).scalar_one()
    total_riders = (
        await db.execute(select(func.count(RiderProfile.id)))
    ).scalar_one()
    total_revenue = (
        await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.status == PaymentStatus.PAID
            )
        )
    ).scalar_one()
    delivered_count = (
        await db.execute(
            select(func.count(Order.id)).where(Order.status == OrderStatus.DELIVERED)
        )
    ).scalar_one()
    pending_count = (
        await db.execute(
            select(func.count(Order.id)).where(
                Order.status.in_([OrderStatus.PAID, OrderStatus.VENDOR_CONFIRMED,
                                   OrderStatus.PREPARING, OrderStatus.RIDER_ASSIGNED,
                                   OrderStatus.PICKED_UP, OrderStatus.AT_HUB,
                                   OrderStatus.HUB_VERIFIED, OrderStatus.IN_TRANSIT])
            )
        )
    ).scalar_one()

    return {
        "total_users": total_users,
        "total_vendors": total_vendors,
        "total_riders": total_riders,
        "total_orders": total_orders,
        "delivered_orders": delivered_count,
        "active_orders": pending_count,
        "total_revenue_ngn": float(total_revenue),
    }


# ── Users ─────────────────────────────────────────────────────────────────────
@router.get("/users", summary="List all users with optional role filter")
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    role: UserRole | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    query = select(User)
    if role:
        query = query.where(User.role == role)
    count_res = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_res.scalar_one()
    result = await db.execute(
        query.order_by(User.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    users = result.scalars().all()
    return paginate_response(
        [UserPublic.model_validate(u) for u in users], total, page, per_page
    )


@router.patch("/users/{user_id}/activate")
async def activate_user(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.is_active = True
    await db.commit()
    return {"status": "activated", "user_id": str(user_id)}


@router.patch("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.is_active = False
    await db.commit()
    return {"status": "deactivated", "user_id": str(user_id)}


# ── Vendor management ─────────────────────────────────────────────────────────
@router.get("/vendors", summary="List all vendor profiles")
async def list_vendors(
    db: Annotated[AsyncSession, Depends(get_db)],
    approved: bool | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    query = select(VendorProfile)
    if approved is not None:
        query = query.where(VendorProfile.is_approved == approved)
    count_res = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_res.scalar_one()
    result = await db.execute(
        query.order_by(VendorProfile.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    vendors = result.scalars().all()
    return paginate_response(
        [VendorProfileOut.model_validate(v) for v in vendors], total, page, per_page
    )


@router.post("/vendors/{vendor_id}/approve")
async def approve_vendor(
    vendor_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(VendorProfile).where(VendorProfile.id == vendor_id))
    vendor = result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found.")
    vendor.is_approved = True
    await db.commit()
    return {"status": "approved", "vendor_id": str(vendor_id)}


@router.post("/vendors/{vendor_id}/suspend")
async def suspend_vendor(
    vendor_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(VendorProfile).where(VendorProfile.id == vendor_id))
    vendor = result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found.")
    vendor.is_approved = False
    await db.commit()
    return {"status": "suspended", "vendor_id": str(vendor_id)}


# ── Rider management ──────────────────────────────────────────────────────────
@router.get("/riders", summary="List all riders")
async def list_riders(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    count_res = await db.execute(select(func.count(RiderProfile.id)))
    total = count_res.scalar_one()
    result = await db.execute(
        select(RiderProfile)
        .order_by(RiderProfile.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    riders = result.scalars().all()
    return paginate_response(
        [RiderProfileOut.model_validate(r) for r in riders], total, page, per_page
    )


@router.post("/riders/{rider_id}/approve")
async def approve_rider(
    rider_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(RiderProfile).where(RiderProfile.id == rider_id))
    rider = result.scalar_one_or_none()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found.")
    rider.is_approved = True
    await db.commit()
    return {"status": "approved", "rider_id": str(rider_id)}


# ── Agent management ──────────────────────────────────────────────────────────
@router.get("/agents", summary="List all agent-role users with hub assignment status")
async def list_agents(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    query = select(User).where(User.role == UserRole.AGENT)
    count_res = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_res.scalar_one()
    result = await db.execute(
        query.order_by(User.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    agents = result.scalars().all()

    # Fetch hub assignments for all returned agents in one query
    agent_ids = [a.id for a in agents]
    hub_res = await db.execute(
        select(AgentHubStaff).where(AgentHubStaff.user_id.in_(agent_ids))
    )
    hub_map: dict[uuid.UUID, uuid.UUID] = {
        s.user_id: s.hub_id for s in hub_res.scalars().all()
    }

    return paginate_response(
        [
            {
                **UserPublic.model_validate(a).model_dump(),
                "hub_id": str(hub_map[a.id]) if a.id in hub_map else None,
                "assigned_to_hub": a.id in hub_map,
            }
            for a in agents
        ],
        total,
        page,
        per_page,
    )


@router.delete(
    "/hubs/{hub_id}/staff/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove agent from hub",
)
async def remove_staff_from_hub(
    hub_id: uuid.UUID,
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(AgentHubStaff).where(
            AgentHubStaff.hub_id == hub_id,
            AgentHubStaff.user_id == user_id,
        )
    )
    staff = result.scalar_one_or_none()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff assignment not found.")
    await db.delete(staff)
    await db.commit()


# ── Orders ────────────────────────────────────────────────────────────────────
@router.get("/orders", summary="View all platform orders")
async def all_orders(
    db: Annotated[AsyncSession, Depends(get_db)],
    order_status: OrderStatus | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    query = select(Order)
    if order_status:
        query = query.where(Order.status == order_status)
    count_res = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_res.scalar_one()
    result = await db.execute(
        query.order_by(Order.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    orders = result.scalars().all()
    return paginate_response(
        [OrderSummary.model_validate(o) for o in orders], total, page, per_page
    )


@router.post("/orders/{order_id}/assign-rider", summary="Assign a rider to a VENDOR_CONFIRMED order")
async def assign_rider_to_order(
    order_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    rider_id: uuid.UUID = Query(..., description="ID of the approved, available rider"),
):
    svc = OrderService(db)
    order = await svc.assign_rider(order_id, rider_id)
    return OrderOut.model_validate(order)


@router.get("/orders/{order_id}/available-riders", summary="List available approved riders for assignment")
async def available_riders_for_order(
    order_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
):
    """Returns approved + available riders, ordered by rating desc."""
    from sqlalchemy.orm import selectinload
    count_res = await db.execute(
        select(func.count(RiderProfile.id)).where(
            RiderProfile.is_approved == True,
            RiderProfile.is_available == True,
        )
    )
    total = count_res.scalar_one()
    result = await db.execute(
        select(RiderProfile)
        .where(RiderProfile.is_approved == True, RiderProfile.is_available == True)
        .options(selectinload(RiderProfile.user))
        .order_by(RiderProfile.rating.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    riders = result.scalars().all()
    return paginate_response(
        [RiderProfileOut.model_validate(r) for r in riders], total, page, per_page
    )


@router.get("/orders/{order_id}/live-track", summary="Real-time order tracking data for admin dashboard")
async def order_live_track(
    order_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Returns full tracking snapshot for a single order:
    stage timestamps, actor details (customer/vendor/rider/hub),
    and live rider GPS coordinates for map polling.
    """
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(Order)
        .options(
            selectinload(Order.customer),
            selectinload(Order.vendor),
            selectinload(Order.rider).selectinload(RiderProfile.user),
            selectinload(Order.agent_hub),
            selectinload(Order.items),
        )
        .where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    def _f(val):
        return float(val) if val is not None else None

    customer = order.customer
    vendor   = order.vendor
    rider    = order.rider
    hub      = order.agent_hub

    return {
        "order_id":          str(order.id),
        "reference":         order.reference,
        "status":            order.status.value,
        "total_amount":      _f(order.total_amount),
        "subtotal":          _f(order.subtotal),
        "delivery_fee":      _f(order.delivery_fee),
        "hub_fee":           _f(order.hub_fee),
        "delivery_address":  order.delivery_address,
        "delivery_latitude":  _f(order.delivery_latitude),
        "delivery_longitude": _f(order.delivery_longitude),
        "delivery_notes":    order.delivery_notes,
        "cancellation_reason": order.cancellation_reason,
        "dispute_reason":    order.dispute_reason,
        # Stage timestamps
        "created_at":         order.created_at.isoformat() if order.created_at else None,
        "vendor_accepted_at": order.vendor_accepted_at.isoformat() if order.vendor_accepted_at else None,
        "vendor_rejected_at": order.vendor_rejected_at.isoformat() if order.vendor_rejected_at else None,
        "rider_assigned_at":  order.rider_assigned_at.isoformat() if order.rider_assigned_at else None,
        "picked_up_at":       order.picked_up_at.isoformat() if order.picked_up_at else None,
        "hub_verified_at":    order.hub_verified_at.isoformat() if order.hub_verified_at else None,
        "in_transit_at":      order.in_transit_at.isoformat() if order.in_transit_at else None,
        "delivered_at":       order.delivered_at.isoformat() if order.delivered_at else None,
        # Items
        "items": [
            {"name": i.product_name, "qty": i.quantity, "price": _f(i.unit_price), "subtotal": _f(i.subtotal)}
            for i in (order.items or [])
        ],
        # Actors
        "customer": {
            "name":  f"{customer.first_name} {customer.last_name}" if customer else "Unknown",
            "phone": customer.phone if customer else None,
        } if customer else None,
        "vendor": {
            "name":    vendor.business_name,
            "address": vendor.business_address,
            "latitude":  _f(vendor.latitude),
            "longitude": _f(vendor.longitude),
        } if vendor else None,
        "rider": {
            "name":      f"{rider.user.first_name} {rider.user.last_name}" if rider and rider.user else "Unknown",
            "phone":     rider.user.phone if rider and rider.user else None,
            "vehicle":   rider.vehicle_type.value if rider else None,
            "plate":     rider.plate_number if rider else None,
            "latitude":  _f(rider.current_latitude) if rider else None,
            "longitude": _f(rider.current_longitude) if rider else None,
            "rating":    _f(rider.rating) if rider else None,
        } if rider else None,
        "hub": {
            "name":      hub.name,
            "address":   hub.address,
            "area":      hub.area,
            "latitude":  _f(hub.latitude),
            "longitude": _f(hub.longitude),
        } if hub else None,
    }


@router.get("/orders/{order_id}/map-data", summary="Get vendor + rider location data for map-based assignment")
async def order_map_data(
    order_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Returns the order's vendor profile (with lat/lng) and all available
    riders (with names and GPS coordinates) for map-based rider assignment.
    """
    from sqlalchemy.orm import selectinload

    # Load the order with its vendor profile
    order_res = await db.execute(
        select(Order)
        .options(selectinload(Order.vendor))
        .where(Order.id == order_id)
    )
    order = order_res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    vendor = order.vendor
    vendor_data = None
    if vendor:
        vendor_data = {
            "id": str(vendor.id),
            "business_name": vendor.business_name,
            "business_address": vendor.business_address,
            "latitude": float(vendor.latitude) if vendor.latitude is not None else None,
            "longitude": float(vendor.longitude) if vendor.longitude is not None else None,
        }

    # Load available riders with their user info
    riders_res = await db.execute(
        select(RiderProfile)
        .where(RiderProfile.is_approved == True, RiderProfile.is_available == True)
        .options(selectinload(RiderProfile.user))
        .order_by(RiderProfile.rating.desc())
        .limit(100)
    )
    riders = riders_res.scalars().all()

    rider_list = []
    for r in riders:
        rider_list.append({
            "id": str(r.id),
            "user_id": str(r.user_id),
            "name": f"{r.user.first_name} {r.user.last_name}" if r.user else "Unknown",
            "vehicle_type": r.vehicle_type.value,
            "plate_number": r.plate_number,
            "current_latitude": float(r.current_latitude) if r.current_latitude is not None else None,
            "current_longitude": float(r.current_longitude) if r.current_longitude is not None else None,
            "is_available": r.is_available,
            "rating": float(r.rating),
            "total_deliveries": r.total_deliveries,
        })

    return {
        "order_id": str(order_id),
        "reference": order.reference,
        "delivery_address": order.delivery_address,
        "vendor": vendor_data,
        "riders": rider_list,
    }


# ── Agent Hubs ────────────────────────────────────────────────────────────────
@router.post(
    "/hubs",
    response_model=AgentHubOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new agent hub",
)
async def create_hub(
    data: AgentHubCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    hub = AgentHub(**data.model_dump())
    db.add(hub)
    await db.commit()
    await db.refresh(hub)
    return AgentHubOut.model_validate(hub)


@router.get("/hubs", response_model=list[AgentHubOut], summary="List all agent hubs")
async def list_hubs(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(AgentHub).order_by(AgentHub.name))
    return [AgentHubOut.model_validate(h) for h in result.scalars().all()]


@router.post("/hubs/{hub_id}/staff/{user_id}", summary="Assign agent to hub")
async def assign_staff_to_hub(
    hub_id: uuid.UUID,
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    staff = AgentHubStaff(user_id=user_id, hub_id=hub_id)
    db.add(staff)
    await db.commit()
    return {"status": "assigned", "hub_id": str(hub_id), "user_id": str(user_id)}


# ── Payments ──────────────────────────────────────────────────────────────────
@router.get("/payments", summary="List all payments")
async def list_payments(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    count_res = await db.execute(select(func.count(Payment.id)))
    total = count_res.scalar_one()
    result = await db.execute(
        select(Payment)
        .order_by(Payment.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    payments = result.scalars().all()
    return paginate_response(
        [PaymentOut.model_validate(p) for p in payments], total, page, per_page
    )


@router.get("/escrows", summary="View all escrow records")
async def list_escrows(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    count_res = await db.execute(select(func.count(Escrow.id)))
    total = count_res.scalar_one()
    result = await db.execute(
        select(Escrow)
        .order_by(Escrow.held_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    escrows = result.scalars().all()
    return paginate_response(
        [EscrowOut.model_validate(e) for e in escrows], total, page, per_page
    )
