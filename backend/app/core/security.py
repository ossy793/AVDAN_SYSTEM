"""
JWT generation / verification and password hashing.
All cryptographic operations are centralised here.
"""
import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.config import settings

logger = logging.getLogger(__name__)

# ── Password hashing ──────────────────────────────────────────────────────────
# Using bcrypt directly — passlib 1.7.4 is incompatible with bcrypt >=4.x


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT ───────────────────────────────────────────────────────────────────────
def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    """
    Args:
        subject: user UUID as string
        extra:   additional claims (e.g. {"role": "rider"})
    """
    expire = _now_utc() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": _now_utc(),
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str) -> str:
    expire = _now_utc() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": _now_utc(),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Returns decoded payload.
    Raises JWTError on invalid / expired tokens — callers must handle it.
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


# ── Monnify webhook verification ──────────────────────────────────────────────
def verify_monnify_signature(raw_body: bytes, signature_header: str) -> bool:
    """
    Verify that the webhook payload genuinely originates from Monnify.
    Uses HMAC-SHA512 with the Monnify secret key.
    """
    expected = hmac.new(
        settings.MONNIFY_SECRET_KEY.encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
