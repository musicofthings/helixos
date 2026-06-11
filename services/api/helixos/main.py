"""FastAPI application entrypoint for HelixOS."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException

from helixos.ai.router import router as ai_router
from helixos.audit.router import router as audit_router
from helixos.audit.service import audit_service, build_audit_store
from helixos.auth.router import router as auth_router
from helixos.db.session import init_db
from helixos.db.settings import get_database_settings
from helixos.modules.router import router as modules_router
from helixos.eln.router import router as eln_router
from helixos.mcp.router import router as mcp_router
from helixos.molecular.router import router as molecular_router
from helixos.errors import http_exception_handler


def create_app() -> FastAPI:
    """Create and configure the HelixOS API application."""
    db_settings = get_database_settings()
    if db_settings.is_configured:
        init_db(db_settings)

    audit_service.use_store(build_audit_store(db_settings))

    app = FastAPI(
        title="HelixOS API",
        version="0.1.0",
        description="AI-native laboratory management and molecular biology platform.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            "http://127.0.0.1:8765",
            "http://localhost:8765",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    @app.head("/health", tags=["system"])
    def health() -> dict[str, str]:
        """Return service health for load balancers and deployment checks."""
        return {"status": "ok"}

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
