"""
ADVAN Logistics Platform — FastAPI entry point.
"""
import logging
import logging.handlers
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.core.exceptions import ADVANException
from app.database import init_db
from app.routers import auth, customer, vendor, rider, agent, admin, payment, upload


def _configure_logging() -> None:
    """Set up console + rotating file logging."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s — %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    # Console handler (already exists via basicConfig if called, replace it)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    # Rotating app log — 10 MB per file, keep 5 backups
    app_file = logging.handlers.RotatingFileHandler(
        log_dir / "advan.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    app_file.setFormatter(fmt)
    app_file.setLevel(logging.INFO)

    # Error-only log — easier to monitor in production
    err_file = logging.handlers.RotatingFileHandler(
        log_dir / "errors.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    err_file.setFormatter(fmt)
    err_file.setLevel(logging.ERROR)

    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(app_file)
    root.addHandler(err_file)


_configure_logging()
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────
async def _seed_admin() -> None:
    """
    If ADMIN_EMAIL and ADMIN_PASSWORD are set in the environment,
    create the admin account on first boot if it doesn't already exist.
    Safe to run repeatedly — skips silently if email already exists.
    """
    import os, uuid, bcrypt
    from datetime import datetime, timezone
    from sqlalchemy import text
    from app.database import AsyncSessionLocal

    email    = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "").strip()
    if not email or not password:
        return

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            text("SELECT id FROM users WHERE email = :e"), {"e": email}
        )).fetchone()
        if row:
            return  # already exists

        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user_id = uuid.uuid4()
        now = datetime.now(tz=timezone.utc)
        first = os.environ.get("ADMIN_FIRST_NAME", "Admin")
        last  = os.environ.get("ADMIN_LAST_NAME", "User")
        phone = os.environ.get("ADMIN_PHONE", "+2340000000000")

        await db.execute(text("""
            INSERT INTO users
                (id, email, phone, first_name, last_name,
                 password_hash, role, extra_roles, is_active, is_verified,
                 created_at, updated_at)
            VALUES
                (:id, :email, :phone, :first, :last,
                 :pw, 'admin', '{}', true, true, :now, :now)
        """), {"id": str(user_id), "email": email, "phone": phone,
               "first": first, "last": last, "pw": pw_hash, "now": now})

        await db.execute(text("""
            INSERT INTO wallets (id, user_id, balance, ledger_balance, currency, updated_at)
            VALUES (:id, :uid, 0, 0, 'NGN', :now)
        """), {"id": str(uuid.uuid4()), "uid": str(user_id), "now": now})

        await db.commit()
        logger.info("Admin account created for %s", email)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ADVAN Platform starting up…")
    await init_db()
    await _seed_admin()
    yield
    logger.info("ADVAN Platform shutting down.")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Central backend for the ADVAN Logistics & Marketplace platform. "
        "Serves customers, vendors, riders, agent hubs, and admins via RBAC."
    ),
    lifespan=lifespan,
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url="/api/redoc" if settings.DEBUG else None,
    openapi_url="/api/openapi.json" if settings.DEBUG else None,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global error handler ──────────────────────────────────────────────────────
@app.exception_handler(ADVANException)
async def advan_exception_handler(request: Request, exc: ADVANException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error: %s %s — %s", request.method, request.url, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again."},
    )


# ── API Routers ───────────────────────────────────────────────────────────────
app.include_router(auth.router,     prefix="/api/auth",    tags=["Authentication"])
app.include_router(customer.router, prefix="/api/customer", tags=["Customer"])
app.include_router(vendor.router,   prefix="/api/vendor",  tags=["Vendor"])
app.include_router(rider.router,    prefix="/api/rider",   tags=["Rider"])
app.include_router(agent.router,    prefix="/api/agent",   tags=["Agent Hub"])
app.include_router(admin.router,    prefix="/api/admin",   tags=["Admin"])
app.include_router(payment.router,  prefix="/api/payment", tags=["Payment"])
app.include_router(upload.router,   prefix="/api/upload",  tags=["Upload"])


# ── Static file serving (uploads) ────────────────────────────────────────────
_upload_dir = Path(settings.UPLOAD_DIR)
_upload_dir.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_upload_dir)), name="uploads")


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["System"])
async def health_check():
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "platform": settings.APP_NAME,
    }
