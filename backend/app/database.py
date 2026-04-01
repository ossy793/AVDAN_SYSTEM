import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)

# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,          # drops stale connections before checkout
    pool_recycle=3600,           # recycle connections every hour
)

# ── Session Factory ───────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ── Base ──────────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Dependency ────────────────────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Init ──────────────────────────────────────────────────────────────────────
async def init_db() -> None:
    """Create all tables and apply incremental migrations on startup."""
    from sqlalchemy import text
    # Import all models so metadata is populated before create_all
    from app.models import (  # noqa: F401
        user, vendor, rider, agent_hub, product, order,
        payment, wallet, notification,
    )
    async with engine.begin() as conn:
        # 1. Create all tables that don't exist yet
        await conn.run_sync(Base.metadata.create_all)

        # 2. Incremental schema migrations — all idempotent (IF NOT EXISTS / DO EXCEPTION)
        migrations = [
            # Order stage timestamps
            """
            ALTER TABLE orders
              ADD COLUMN IF NOT EXISTS vendor_accepted_at TIMESTAMPTZ,
              ADD COLUMN IF NOT EXISTS vendor_rejected_at TIMESTAMPTZ,
              ADD COLUMN IF NOT EXISTS rider_assigned_at  TIMESTAMPTZ,
              ADD COLUMN IF NOT EXISTS picked_up_at       TIMESTAMPTZ,
              ADD COLUMN IF NOT EXISTS hub_verified_at    TIMESTAMPTZ,
              ADD COLUMN IF NOT EXISTS in_transit_at      TIMESTAMPTZ;
            """,
            # vendor_rejected enum value
            """
            DO $$ BEGIN
              ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'vendor_rejected';
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
            """,
            # Multi-role support
            """
            ALTER TABLE users
              ADD COLUMN IF NOT EXISTS extra_roles TEXT[] NOT NULL DEFAULT '{}';
            """,
            # Vendor location coordinates
            """
            ALTER TABLE vendor_profiles
              ADD COLUMN IF NOT EXISTS latitude  NUMERIC(10,7),
              ADD COLUMN IF NOT EXISTS longitude NUMERIC(10,7);
            """,
        ]
        for sql in migrations:
            await conn.execute(text(sql))

    logger.info("Database tables initialised and migrations applied.")
