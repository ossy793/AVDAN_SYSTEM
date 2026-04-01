"""
Role-Based Access Control (RBAC).

FastAPI dependencies that gate endpoints by role.
Usage:
    @router.get("/orders", dependencies=[Depends(require_role(UserRole.VENDOR))])
"""
import logging
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.database import get_db
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Decode the JWT bearer token and return the authenticated User ORM object.
    Raises 401 on any failure.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise credentials_exception
        user_id_str: str | None = payload.get("sub")
        if not user_id_str:
            raise credentials_exception
        user_id = uuid.UUID(user_id_str)
    except (JWTError, ValueError):
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user: User | None = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: UserRole):
    """
    Dependency factory.  Inject after get_current_user.
    Checks both the primary role and any extra_roles the user has.

    Example:
        @router.post("/confirm", dependencies=[Depends(require_role(UserRole.AGENT))])
    """
    async def _check(current_user: CurrentUser) -> User:
        user_roles = set(current_user.roles)  # uses the .roles property
        if not any(r.value in user_roles for r in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access denied. Required role(s): "
                    f"{[r.value for r in roles]}."
                ),
            )
        return current_user

    return _check


def require_verified():
    """Ensure the account has completed email / phone verification."""
    async def _check(current_user: CurrentUser) -> User:
        if not current_user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account not verified. Please complete verification.",
            )
        return current_user

    return _check
