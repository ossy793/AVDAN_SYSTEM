"""
Agent Hub routes — package verification, inter-hub dispatch.
All routes require JWT with role=AGENT.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.rbac import CurrentUser, require_role
from app.database import get_db
from app.models.agent_hub import AgentHub, AgentHubStaff
from app.models.notification import Message
from app.models.order import OrderStatus
from app.models.rider import RiderProfile
from app.models.user import UserRole
from app.schemas.notification import MessageCreate, MessageOut
from app.schemas.order import OrderOut, OrderSummary
from app.schemas.user import AgentHubOut
from app.services.order_service import OrderService
from app.utils.helpers import paginate_response

router = APIRouter(dependencies=[Depends(require_role(UserRole.AGENT))])


async def _get_hub_id(current_user, db) -> uuid.UUID:
    """Resolve the agent's assigned hub."""
    result = await db.execute(
        select(AgentHubStaff).where(AgentHubStaff.user_id == current_user.id)
    )
    staff = result.scalar_one_or_none()
    if not staff:
        raise HTTPException(status_code=422, detail="Agent is not assigned to a hub.")
    return staff.hub_id


# ── Hub orders ────────────────────────────────────────────────────────────────
@router.get("/orders", summary="View orders at my hub")
async def hub_orders(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    order_status: OrderStatus | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
):
    hub_id = await _get_hub_id(current_user, db)
    svc = OrderService(db)
    orders, total = await svc.get_hub_orders(hub_id, order_status, page, per_page)
    return paginate_response(
        [OrderSummary.model_validate(o) for o in orders], total, page, per_page
    )


@router.get("/orders/{order_id}", response_model=OrderOut)
async def get_hub_order(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    hub_id = await _get_hub_id(current_user, db)
    svc = OrderService(db)
    order = await svc.get_order(order_id)
    if order.agent_hub_id != hub_id:
        raise HTTPException(status_code=403, detail="Order not at your hub.")
    return OrderOut.model_validate(order)


@router.post(
    "/orders/{order_id}/verify",
    response_model=OrderOut,
    summary="Verify and package the order at hub",
)
async def verify_order(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Agent physically checks contents against the order manifest and marks verified.
    This unlocks the IN_TRANSIT step for the rider.
    """
    hub_id = await _get_hub_id(current_user, db)
    svc = OrderService(db)
    order = await svc.get_order(order_id)
    if order.agent_hub_id != hub_id:
        raise HTTPException(status_code=403, detail="Order not at your hub.")
    order = await svc.transition(order_id, OrderStatus.HUB_VERIFIED, current_user)
    return OrderOut.model_validate(order)


# ── Rider assignment ──────────────────────────────────────────────────────────
@router.get("/riders", summary="List available approved riders for dispatch")
async def available_riders(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    from sqlalchemy import func as sa_func
    count_res = await db.execute(
        select(sa_func.count(RiderProfile.id)).where(
            RiderProfile.is_available == True,
            RiderProfile.is_approved == True,
        )
    )
    total = count_res.scalar_one()

    result = await db.execute(
        select(RiderProfile)
        .options(selectinload(RiderProfile.user))
        .where(
            RiderProfile.is_available == True,
            RiderProfile.is_approved == True,
        )
        .order_by(RiderProfile.rating.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    riders = result.scalars().all()
    return paginate_response(
        [
            {
                "id": str(r.id),
                "name": f"{r.user.first_name} {r.user.last_name}",
                "vehicle_type": r.vehicle_type.value,
                "plate_number": r.plate_number or "—",
                "rating": float(r.rating),
            }
            for r in riders
        ],
        total,
        page,
        per_page,
    )


@router.post(
    "/orders/{order_id}/assign-rider",
    response_model=OrderOut,
    summary="Assign a delivery rider to a hub-verified order",
)
async def assign_delivery_rider(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    rider_id: uuid.UUID = Query(..., description="RiderProfile.id of the rider to assign"),
):
    hub_id = await _get_hub_id(current_user, db)
    svc = OrderService(db)
    order = await svc.get_order(order_id)

    if order.agent_hub_id != hub_id:
        raise HTTPException(status_code=403, detail="Order not at your hub.")
    if order.status != OrderStatus.HUB_VERIFIED:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Order must be 'hub_verified' to assign a rider. "
                f"Current: '{order.status.value}'."
            ),
        )

    # Assign via service layer so notifications are sent and rider availability is updated
    order = await svc.assign_rider(order_id, rider_id)
    return OrderOut.model_validate(order)


# ── Hub info ──────────────────────────────────────────────────────────────────
@router.get("/hub", response_model=AgentHubOut, summary="Get this agent's hub information")
async def get_my_hub(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    hub_id = await _get_hub_id(current_user, db)
    result = await db.execute(select(AgentHub).where(AgentHub.id == hub_id))
    hub = result.scalar_one_or_none()
    if not hub:
        raise HTTPException(status_code=404, detail="Hub not found.")
    return AgentHubOut.model_validate(hub)


# ── Messaging ─────────────────────────────────────────────────────────────────
@router.post("/messages", response_model=MessageOut)
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
