"""Utility helpers used across the platform."""
import math
import re
import uuid
from datetime import datetime, timezone


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two GPS coordinates (km)."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def sanitise_phone(phone: str) -> str:
    """Normalise Nigerian phone numbers to international format."""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("0") and len(digits) == 11:
        return "+234" + digits[1:]
    if digits.startswith("234") and len(digits) == 13:
        return "+" + digits
    return phone


def mask_account_number(account: str) -> str:
    """Return last 4 digits of bank account, rest masked."""
    if len(account) < 4:
        return "****"
    return "*" * (len(account) - 4) + account[-4:]


def paginate_response(items: list, total: int, page: int, per_page: int) -> dict:
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": math.ceil(total / per_page) if per_page else 1,
    }
