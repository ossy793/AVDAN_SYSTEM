import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import UserRole
from app.models.rider import VehicleType


# ── Registration ──────────────────────────────────────────────────────────────
class UserRegister(BaseModel):
    email: EmailStr
    phone: str = Field(..., min_length=10, max_length=15, pattern=r"^\+?[0-9]{10,15}$")
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: UserRole
    roles: list[str] = []   # all roles: primary + extra
    user_id: uuid.UUID


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# ── Public user info ──────────────────────────────────────────────────────────
class UserPublic(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    email: EmailStr
    phone: str
    first_name: str
    last_name: str
    role: UserRole
    roles: list[str] = []   # all roles: primary + extra (from User.roles property)
    is_active: bool
    is_verified: bool
    created_at: datetime

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class UserUpdate(BaseModel):
    first_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    phone: str | None = Field(None, pattern=r"^\+?[0-9]{10,15}$")


# ── Vendor profile ────────────────────────────────────────────────────────────
class VendorProfileCreate(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=200)
    business_address: str = Field(..., min_length=5)
    business_type: str | None = Field(None, max_length=100)
    description: str | None = None
    bank_account_number: str | None = Field(None, max_length=20)
    bank_code: str | None = Field(None, max_length=10)
    bank_name: str | None = Field(None, max_length=100)


class VendorProfileUpdate(BaseModel):
    business_name: str | None = Field(None, max_length=200)
    business_address: str | None = None
    business_type: str | None = Field(None, max_length=100)
    description: str | None = None
    is_open: bool | None = None
    bank_account_number: str | None = Field(None, max_length=20)
    bank_code: str | None = Field(None, max_length=10)
    bank_name: str | None = Field(None, max_length=100)


class VendorProfileOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID
    business_name: str
    business_address: str
    business_type: str | None
    description: str | None
    logo_url: str | None
    is_approved: bool
    is_open: bool
    rating: float
    total_orders: int
    bank_name: str | None
    paystack_recipient_code: str | None
    latitude: float | None
    longitude: float | None
    created_at: datetime


# ── Rider profile ─────────────────────────────────────────────────────────────
class RiderProfileCreate(BaseModel):
    vehicle_type: VehicleType = VehicleType.MOTORCYCLE
    plate_number: str | None = Field(None, max_length=20)
    bank_account_number: str | None = Field(None, max_length=20)
    bank_code: str | None = Field(None, max_length=10)
    bank_name: str | None = Field(None, max_length=100)


class RiderProfileUpdate(BaseModel):
    vehicle_type: VehicleType | None = None
    plate_number: str | None = Field(None, max_length=20)
    is_available: bool | None = None
    bank_account_number: str | None = Field(None, max_length=20)
    bank_code: str | None = Field(None, max_length=10)
    bank_name: str | None = Field(None, max_length=100)


class RiderLocationUpdate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class RiderProfileOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID
    vehicle_type: VehicleType
    plate_number: str | None
    current_latitude: float | None
    current_longitude: float | None
    is_available: bool
    is_approved: bool
    rating: float
    total_deliveries: int
    bank_name: str | None
    created_at: datetime


# ── Agent hub ─────────────────────────────────────────────────────────────────
class AgentHubCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    address: str = Field(..., min_length=5)
    area: str | None = Field(None, max_length=100)
    phone: str | None = Field(None, max_length=20)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    capacity: int = Field(100, gt=0)


class AgentHubOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    address: str
    area: str | None
    state: str
    latitude: float | None
    longitude: float | None
    phone: str | None
    is_active: bool
    capacity: int
    created_at: datetime
