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
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ADVAN Platform starting up…")
    await init_db()
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
