"""Stable API error helpers."""

from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def api_error(status_code: int, code: str, message: str, details: dict[str, Any] | None = None) -> HTTPException:
    """Create an HTTP exception that renders through the stable error envelope."""
    return HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
            "details": details or {},
        },
    )


async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Render FastAPI HTTP exceptions with the HelixOS error envelope."""
    if isinstance(exc.detail, dict) and {"code", "message", "details"}.issubset(exc.detail):
        payload = exc.detail
    else:
        payload = {
            "code": "http_error",
            "message": str(exc.detail),
            "details": {},
        }

    return JSONResponse(
        status_code=exc.status_code,
        content={"error": payload},
        headers=exc.headers,
    )
