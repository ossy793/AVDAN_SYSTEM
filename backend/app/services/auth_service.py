"""
Authentication & account lifecycle service.
Handles registration, login, token refresh, and profile setup.
"""
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExists, InvalidCredentials, NotFound
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.agent_hub import AgentHub, AgentHubStaff
from app.models.rider import RiderProfile
from app.models.user import User, UserRole
from app.models.vendor import VendorProfile
from app.models.wallet import Wallet
from app.schemas.user import (
    RiderProfileCreate,
    TokenResponse,
    UserLogin,
    UserRegister,
    VendorProfileCreate,
)
from app.services.wallet_service import WalletService

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Registration ──────────────────────────────────────────────────────
    async def register(self, data: UserRegister) -> User:
        from fastapi import HTTPException, status as http_status

        # Admin accounts can only be created via backend scripts, never via API
        if data.role == UserRole.ADMIN:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Admin accounts cannot be created through registration. Contact the platform administrator.",
            )

        # Check if email already exists
        result = await self.db.execute(select(User).where(User.email == data.email))
        existing_user: User | None = result.scalar_one_or_none()

        if existing_user:
            # If the same role → straightforward duplicate
            if data.role == existing_user.role:
                raise AlreadyExists("Email")
            # Different role → let them add this role to their existing account.
            # Require correct password so only the account owner can do this.
            if not verify_password(data.password, existing_user.password_hash):
                raise AlreadyExists("Email")  # don't hint at the real reason
            # Add the new role to extra_roles if not already present
            current_extra = list(existing_user.extra_roles or [])
            if data.role.value not in current_extra:
                current_extra.append(data.role.value)
                existing_user.extra_roles = current_extra
                await self.db.commit()
                await self.db.refresh(existing_user)
                logger.info(
                    "Added role '%s' to existing user: %s",
                    data.role.value, existing_user.email,
                )
            return existing_user

        # New user — check phone uniqueness
        existing_phone = await self.db.execute(
            select(User).where(User.phone == data.phone)
        )
        if existing_phone.scalar_one_or_none():
            raise AlreadyExists("Phone number")

        user = User(
            email=data.email.lower().strip(),
            phone=data.phone,
            first_name=data.first_name.strip(),
            last_name=data.last_name.strip(),
            password_hash=hash_password(data.password),
            role=data.role,
            extra_roles=[],
            is_active=True,
            is_verified=False,
        )
        self.db.add(user)
        await self.db.flush()  # get the UUID assigned

        # Create wallet for every new user
        wallet_svc = WalletService(self.db)
        await wallet_svc.create_wallet(user.id)

        await self.db.commit()
        await self.db.refresh(user)
        logger.info("New user registered: %s [%s]", user.email, user.role.value)
        return user

    # ── Login ─────────────────────────────────────────────────────────────
    async def login(self, data: UserLogin) -> TokenResponse:
        result = await self.db.execute(
            select(User).where(User.email == data.email.lower().strip())
        )
        user: User | None = result.scalar_one_or_none()

        if not user or not verify_password(data.password, user.password_hash):
            raise InvalidCredentials()

        if not user.is_active:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated.",
            )

        all_roles = user.roles  # primary + extra_roles via property
        access_token = create_access_token(
            subject=str(user.id),
            extra={"role": user.role.value, "roles": all_roles},
        )
        refresh_token = create_refresh_token(subject=str(user.id))

        logger.info("User logged in: %s roles=%s", user.email, all_roles)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            role=user.role,
            roles=all_roles,
            user_id=user.id,
        )

    # ── Token refresh ─────────────────────────────────────────────────────
    async def refresh_tokens(self, refresh_token: str) -> TokenResponse:
        from jose import JWTError
        from fastapi import HTTPException, status

        try:
            payload = decode_token(refresh_token)
            if payload.get("type") != "refresh":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type.",
                )
            user_id = uuid.UUID(payload["sub"])
        except (JWTError, ValueError, KeyError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token.",
            )

        result = await self.db.execute(select(User).where(User.id == user_id))
        user: User | None = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive.",
            )

        all_roles = user.roles
        access_token = create_access_token(
            subject=str(user.id),
            extra={"role": user.role.value, "roles": all_roles},
        )
        new_refresh = create_refresh_token(subject=str(user.id))
        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh,
            role=user.role,
            roles=all_roles,
            user_id=user.id,
        )

    # ── Vendor profile setup ──────────────────────────────────────────────
    async def create_vendor_profile(
        self, user: User, data: VendorProfileCreate
    ) -> VendorProfile:
        if UserRole.VENDOR.value not in user.roles:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only vendor accounts can create a vendor profile.",
            )
        existing = await self.db.execute(
            select(VendorProfile).where(VendorProfile.user_id == user.id)
        )
        if existing.scalar_one_or_none():
            raise AlreadyExists("Vendor profile")

        profile = VendorProfile(
            user_id=user.id,
            business_name=data.business_name,
            business_address=data.business_address,
            business_type=data.business_type,
            description=data.description,
            bank_account_number=data.bank_account_number,
            bank_code=data.bank_code,
            bank_name=data.bank_name,
            is_approved=False,
        )
        self.db.add(profile)
        await self.db.commit()
        await self.db.refresh(profile)
        return profile

    # ── Rider profile setup ───────────────────────────────────────────────
    async def create_rider_profile(
        self, user: User, data: RiderProfileCreate
    ) -> RiderProfile:
        if UserRole.RIDER.value not in user.roles:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only rider accounts can create a rider profile.",
            )
        existing = await self.db.execute(
            select(RiderProfile).where(RiderProfile.user_id == user.id)
        )
        if existing.scalar_one_or_none():
            raise AlreadyExists("Rider profile")

        profile = RiderProfile(
            user_id=user.id,
            vehicle_type=data.vehicle_type,
            plate_number=data.plate_number,
            bank_account_number=data.bank_account_number,
            bank_code=data.bank_code,
            bank_name=data.bank_name,
            is_approved=False,
            is_available=False,
        )
        self.db.add(profile)
        await self.db.commit()
        await self.db.refresh(profile)
        return profile
