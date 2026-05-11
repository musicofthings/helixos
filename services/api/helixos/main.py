"""FastAPI application entrypoint for HelixOS."""

from fastapi import FastAPI
from starlette.exceptions import HTTPException

from helixos.auth.router import router as auth_router
from helixos.modules.router import router as modules_router
from helixos.eln.router import router as eln_router
from helixos.mcp.router import router as mcp_router
from helixos.molecular.router import router as molecular_router
from helixos.errors import http_exception_handler


def create_app() -> FastAPI:
    """Create and configure the HelixOS API application."""
    app = FastAPI(
        title="HelixOS API",
        version="0.1.0",
        description="AI-native laboratory management and molecular biology platform.",
    )

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        """Return service health for load balancers and deployment checks."""
        return {"status": "ok"}

    app.add_exception_handler(HTTPException, http_exception_handler)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(modules_router, prefix="/api/v1")
    app.include_router(eln_router, prefix="/api/v1")
    app.include_router(molecular_router, prefix="/api/v1")
    app.include_router(mcp_router, prefix="/api/v1")
    return app


app = create_app()
