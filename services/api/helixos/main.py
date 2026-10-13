"""FastAPI application entrypoint for HelixOS."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException

from helixos import config
from helixos.ai.router import router as ai_router
from helixos.ai.settings import AISettings
from helixos.audit.router import router as audit_router
from helixos.audit.service import audit_service, build_audit_store
from helixos.auth.router import router as auth_router
from helixos.config import validate_runtime_config
from helixos.db.migrations import MIGRATIONS, applied_versions
from helixos.db.session import get_engine, init_db
from helixos.observability import (
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
    configure_logging,
)
from helixos.pagination import PAGINATION_HEADERS
from helixos.db.settings import get_database_settings
from helixos.modules.router import router as modules_router
from helixos.eln.router import router as eln_router
from helixos.eln.service import build_eln_store, eln_service
from helixos.mcp.router import router as mcp_router
from helixos.molecular.router import router as molecular_router
from helixos.errors import http_exception_handler


logger = logging.getLogger("helixos.api")


def readiness_problem() -> str | None:
    """Why this instance should not receive traffic, or None when it is ready."""
    settings = get_database_settings()
    if not settings.is_configured:
        return None
    try:
        engine = get_engine(settings)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        pending = {name for name, _ in MIGRATIONS} - set(applied_versions(engine))
    except Exception as error:  # any failure here means "not ready"
        return f"database: {type(error).__name__}"
    return f"pending migrations: {sorted(pending)}" if pending else None


def _cors_options() -> dict:
    """CORS policy for the current environment.

    Development also accepts any loopback origin (dev web on :3000 and the
    packaged Electron static UI on an ephemeral port). Hosted environments
    accept only the origins listed in ALLOWED_ORIGINS.
    """
    options: dict = {
        "allow_origins": list(config.allowed_origins()),
        "allow_credentials": True,
        "expose_headers": [*PAGINATION_HEADERS, REQUEST_ID_HEADER],
    }
    if config.is_hosted():
        options["allow_methods"] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
        options["allow_headers"] = [
            "Authorization",
            "Content-Type",
            "Accept",
            REQUEST_ID_HEADER,
        ]
    else:
        options["allow_origin_regex"] = r"https?://(127\.0\.0\.1|localhost)(:\d+)?"
        options["allow_methods"] = ["*"]
        options["allow_headers"] = ["*"]
    return options


def create_app() -> FastAPI:
    """Create and configure the HelixOS API application."""
    configure_logging()
    db_settings = get_database_settings()
    validate_runtime_config(db_settings, AISettings.from_env())
    if db_settings.is_configured:
        init_db(db_settings)

    audit_service.use_store(build_audit_store(db_settings))
    eln_service.use_store(build_eln_store(db_settings))

    docs = config.docs_enabled()
    app = FastAPI(
        title="HelixOS API",
        version="0.1.0",
        description="AI-native laboratory management and molecular biology platform.",
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )

    # Added first = innermost, so CORS still wraps error responses it produces.
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(CORSMiddleware, **_cors_options())

    @app.get("/health", tags=["system"])
    @app.head("/health", tags=["system"])
    def health() -> dict[str, str]:
        """Return service health for load balancers and deployment checks."""
        return {"status": "ok"}

    @app.get("/ready", tags=["system"])
    def ready() -> JSONResponse:
        """Readiness: the database answers and every migration is applied.

        Separate from /health (liveness) so a deploy can wait for a working
        instance and a database outage takes it out of rotation without
        restarting a healthy process.
        """
        problem = readiness_problem()
        if problem is not None:
            logger.warning("not ready", extra={"reason": problem})
            return JSONResponse({"status": "not_ready"}, status_code=503)
        return JSONResponse({"status": "ready"})

    app.add_exception_handler(HTTPException, http_exception_handler)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(modules_router, prefix="/api/v1")
    app.include_router(eln_router, prefix="/api/v1")
    app.include_router(molecular_router, prefix="/api/v1")
    app.include_router(mcp_router, prefix="/api/v1")
    app.include_router(ai_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    return app


app = create_app()
