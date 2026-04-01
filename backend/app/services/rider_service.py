"""
Rider management: location updates, availability, order picking.
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound
from app.models.rider import RiderProfile
from app.models.order import Order, OrderStatus

logger = logging.getLogger(__name__)


class RiderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def update_location(
        self,
        rider_id: uuid.UUID,
        latitude: float,
        longitude: float,
    ) -> RiderProfile:
        result = await self.db.execute(
            select(RiderProfile).where(RiderProfile.user_id == rider_id)
        )
        profile: RiderProfile | None = result.scalar_one_or_none()
        if not profile:
            raise NotFound("Rider profile")

        profile.current_latitude = latitude
        profile.current_longitude = longitude
        profile.location_updated_at = datetime.now(tz=timezone.utc)
        await self.db.commit()
        await self.db.refresh(profile)
        return profile

    async def set_availability(
        self, rider_id: uuid.UUID, available: bool
    ) -> RiderProfile:
        result = await self.db.execute(
            select(RiderProfile).where(RiderProfile.user_id == rider_id)
        )
        profile: RiderProfile | None = result.scalar_one_or_none()
        if not profile:
            raise NotFound("Rider profile")

        profile.is_available = available
        await self.db.commit()
        await self.db.refresh(profile)
        logger.info(
            "Rider %s availability → %s", rider_id, "online" if available else "offline"
        )
        return profile

    async def get_available_riders(self) -> list[RiderProfile]:
        result = await self.db.execute(
            select(RiderProfile).where(
                and_(
                    RiderProfile.is_available == True,
                    RiderProfile.is_approved == True,
                )
            )
        )
        return result.scalars().all()

    async def get_current_assignment(self, rider_user_id: uuid.UUID) -> Order | None:
        """Returns the active order currently assigned to this rider."""
        rider_res = await self.db.execute(
            select(RiderProfile).where(RiderProfile.user_id == rider_user_id)
        )
        rider = rider_res.scalar_one_or_none()
        if not rider:
            return None

        active_statuses = [
            OrderStatus.RIDER_ASSIGNED,
            OrderStatus.PICKED_UP,
            OrderStatus.AT_HUB,
            OrderStatus.HUB_VERIFIED,
            OrderStatus.IN_TRANSIT,
        ]
        result = await self.db.execute(
            select(Order).where(
                and_(
                    Order.rider_id == rider.id,
                    Order.status.in_(active_statuses),
                )
            )
        )
        return result.scalar_one_or_none()
