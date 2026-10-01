from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.api import payments, notifications, one_c, admin, catalog, tenant_auth, webhooks, xlsx_import
from app.core.config import settings
from app.db.database import SessionLocal, engine
from app.db.schema_ensure import ensure_tenant_smtp_columns
from app.services.catalog_seed import ensure_super_admin, sync_tenant_green_api_from_env
from alembic import command
from alembic.config import Config
from pathlib import Path
import logging
import re

logger = logging.getLogger(__name__)

# Guarded by "pytest" not being loaded: importing app.main is unavoidable for
# endpoint tests (conftest.py needs the app object), and Sentry's logging
# integration auto-captures any logger.error/.exception call as a real event —
# without this guard, every local `pytest tests/` run quietly reports test
# noise to the actual Sentry project.
import sys

if settings.SENTRY_DSN and "pytest" not in sys.modules:
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        traces_sample_rate=0.1,
    )

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _configure_app_logging() -> None:
    """Логи app.* в терминал: alembic.ini держит root на WARNING, INFO из кода не виден."""
    import os

    if (settings.ENVIRONMENT or "").strip() == "production":
        return

    level_name = (os.getenv("LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )


# Намеренный дубль с CORS_ORIGINS в .env.*: эти домены разрешены всегда,
# независимо от того, что (не) выставлено в ENV на конкретном деплое — страховка
# от «забыли переменную окружения» на одном из трёх окружений. Если меняете
# домен — правьте оба места (здесь и в .env.production/.development/.test).
PROD_CORS_ORIGINS = (
    "https://invoice.metrix.com.ai",
    "https://admin.invoice.metrix.com.ai",
    "https://invoice.dev.metrix.com.ai",
    "https://admin.invoice.dev.metrix.com.ai",
    "https://invoice.test.metrix.com.ai",
    "https://admin.invoice.test.metrix.com.ai",
)


def _production_cors_origins() -> list[str]:
    merged = list(settings.CORS_ORIGINS)
    for origin in PROD_CORS_ORIGINS:
        if origin not in merged:
            merged.append(origin)
    return merged


def _run_alembic_migrations() -> None:
    alembic_cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")


try:
    _run_alembic_migrations()
    # Страховка: если alembic не догнал (версия/ошибка), SMTP-колонки всё равно появятся.
    ensure_tenant_smtp_columns(engine)
    _configure_app_logging()
    logger.info("Database ready")
    db = SessionLocal()
    try:
        ensure_super_admin(db)
        sync_tenant_green_api_from_env(db)
    finally:
        db.close()
except Exception as e:
    logger.error("Database initialization failed: %s", e)
    # Даже при сбое alembic пробуем создать SMTP-колонки — иначе весь портал 500.
    try:
        ensure_tenant_smtp_columns(engine)
    except Exception as ensure_err:
        logger.error("Failed to ensure tenant SMTP columns: %s", ensure_err)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Scheduler живёт в процессе uvicorn (не в отдельном python -c из entrypoint)."""
    from app.scheduler import shutdown_scheduler, start_scheduler

    _configure_app_logging()
    try:
        start_scheduler()
        logger.info("Scheduler started")
    except Exception as exc:
        logger.warning("Scheduler not started: %s", exc)
    yield
    try:
        shutdown_scheduler()
    except Exception as exc:
        logger.warning("Scheduler shutdown failed: %s", exc)


app = FastAPI(
    title="Payment Registry API",
    description="ERP module for rent control - Payment Registry",
    version="1.0.0",
    lifespan=lifespan,
)


_cors_kwargs = {
    "allow_credentials": True,
    "allow_methods": ["GET", "POST", "PATCH", "PUT", "DELETE"],
    "allow_headers": ["Authorization", "Content-Type"],
    "allow_origins": _production_cors_origins(),
}
if settings.ENVIRONMENT == "development":
    _cors_kwargs["allow_origin_regex"] = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"

app.add_middleware(CORSMiddleware, **_cors_kwargs)


def _origin_allowed(origin: str) -> bool:
    if origin in _production_cors_origins():
        return True
    if settings.ENVIRONMENT == "development":
        return bool(
            re.match(r"https?://(localhost|127\.0\.0\.1)(:\d+)?$", origin)
        )
    return False


def _cors_headers_for_request(request: Request) -> dict[str, str]:
    origin = request.headers.get("origin")
    if not origin or not _origin_allowed(origin):
        return {}
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Vary": "Origin",
    }


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
        headers=_cors_headers_for_request(request),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=_cors_headers_for_request(request),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled API error on %s", request.url.path)
    if settings.SENTRY_DSN:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
        headers=_cors_headers_for_request(request),
    )


app.include_router(payments.router, prefix="/api/payments", tags=["payments"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(one_c.router, prefix="/api/1c", tags=["1c"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(catalog.router, prefix="/api/catalog", tags=["catalog"])
app.include_router(tenant_auth.router, prefix="/api/tenant-auth", tags=["tenant-auth"])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["webhooks"])
app.include_router(xlsx_import.router, prefix="/api/xlsx-import", tags=["xlsx-import"])


@app.get("/")
async def root():
    return {"message": "Payment Registry API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "payment-registry-api"}
