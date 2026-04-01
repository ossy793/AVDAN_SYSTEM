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
    """Create all tables on startup (use Alembic for production migrations)."""
    # Import all models so metadata is populated before create_all
    from app.models import (  # noqa: F401
        user, vendor, rider, agent_hub, product, order,
        payment, wallet, notification,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialised.")
