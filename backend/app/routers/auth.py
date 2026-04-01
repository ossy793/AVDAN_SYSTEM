"""
Authentication routes — open endpoints (no JWT required).
POST /api/auth/register
POST /api/auth/login
POST /api/auth/refresh
POST /api/auth/vendor/profile
POST /api/auth/rider/profile
GET  /api/auth/me
"""
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import CurrentUser
from app.database import get_db
from app.schemas.user import (
    RefreshTokenRequest,
    RiderProfileCreate,
    RiderProfileOut,
    TokenResponse,
    UserLogin,
    UserPublic,
    UserRegister,
    VendorProfileCreate,
    VendorProfileOut,
)
from app.services.auth_service import AuthService

router = APIRouter()


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account",
)
async def register(
    data: UserRegister,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = AuthService(db)
    user = await svc.register(data)
    return UserPublic.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive JWT tokens",
)
async def login(
    data: UserLogin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = AuthService(db)
    return await svc.login(data)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Exchange refresh token for new access token",
)
async def refresh(
    body: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = AuthService(db)
    return await svc.refresh_tokens(body.refresh_token)


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Get current authenticated user info",
)
async def me(current_user: CurrentUser):
    return UserPublic.model_validate(current_user)


@router.post(
    "/vendor/profile",
    response_model=VendorProfileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create vendor business profile (vendors only)",
)
async def create_vendor_profile(
    data: VendorProfileCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = AuthService(db)
    profile = await svc.create_vendor_profile(current_user, data)
    return VendorProfileOut.model_validate(profile)


@router.post(
    "/rider/profile",
    response_model=RiderProfileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create rider profile (riders only)",
)
async def create_rider_profile(
    data: RiderProfileCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = AuthService(db)
    profile = await svc.create_rider_profile(current_user, data)
    return RiderProfileOut.model_validate(profile)
