from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ── Application ────────────────────────────────────────────────────────
    APP_NAME: str = "ADVAN Logistics Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ── Security ───────────────────────────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Database ───────────────────────────────────────────────────────────
    DATABASE_URL: str

    # ── Demo mode ──────────────────────────────────────────────────────────
    # Set DEMO_MODE=true to bypass all real Monnify API calls.
    # Payments are auto-confirmed instantly. Safe for investor demos.
    DEMO_MODE: bool = False

    # ── Monnify ────────────────────────────────────────────────────────────
    # In DEMO_MODE these values are never sent to Monnify — defaults are fine.
    # Sandbox base URL: https://sandbox.monnify.com
    # Live base URL:    https://api.monnify.com
    MONNIFY_API_KEY: str = "MK_TEST_demo_key"
    MONNIFY_SECRET_KEY: str = "demo_secret_key"
    MONNIFY_CONTRACT_CODE: str = "demo_contract_code"
    MONNIFY_BASE_URL: str = "https://sandbox.monnify.com"
    # The Monnify virtual wallet account used as the payout source
    MONNIFY_WALLET_ACCOUNT: str = ""
    # URL Monnify redirects to after checkout (your frontend payment callback)
    MONNIFY_REDIRECT_URL: str = "http://localhost:8000/api/payment/verify"

    # ── Platform Financials (NGN) ──────────────────────────────────────────
    PLATFORM_FEE_PERCENTAGE: float = 5.0   # % of order subtotal
    DELIVERY_BASE_FEE: float = 500.0        # NGN flat base delivery fee
    HUB_FEE: float = 100.0                  # NGN per-order hub processing fee

    # ── File uploads ───────────────────────────────────────────────────────
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 5

    # ── CORS ───────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "https://avdan-system.vercel.app",
        "https://avdan-system-9ksg.vercel.app",
        "https://avdan-admin.vercel.app",
        "https://avdan-vendor.vercel.app",
        "https://avdan-riders.vercel.app",
        "https://avdan-agent.vercel.app",
    ]

    # ── Notification Providers (abstract hooks) ────────────────────────────
    SMS_PROVIDER_API_KEY: str = ""
    WHATSAPP_PROVIDER_API_KEY: str = ""


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
