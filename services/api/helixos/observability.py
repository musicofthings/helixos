"""Structured logging and request correlation.

Every request gets a ``request_id`` (taken from a sane inbound ``X-Request-ID`` or
generated), echoed in the response header and the error envelope, and attached to
every log record emitted while handling it, including work dispatched to the
threadpool. Long-running units add ``job_id`` / ``run_id`` the same way.

Output is one JSON object per line by default (``HELIX_LOG_FORMAT=text`` for
human-readable dev output); level comes from ``HELIX_LOG_LEVEL``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_INBOUND_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# A mutable dict, not scalar vars: values bound inside a threadpool dependency
# (e.g. the authenticated actor) must be visible to the middleware's access log,
# and threadpool contexts are copies. Mutating the shared dict crosses that gap.
_log_context: ContextVar[dict[str, Any] | None] = ContextVar("helix_log_context", default=None)

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


def bind(**fields: Any) -> None:
    """Attach fields (``actor``, ``job_id`` ...) to every later log record of this request."""
    context = _log_context.get()
    if context is not None:
        context.update(fields)


def current_request_id() -> str | None:
    context = _log_context.get()
    return context.get("request_id") if context else None


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in (_log_context.get() or {}).items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Install the structured handler on the ``helixos`` logger tree (idempotent)."""
    logger = logging.getLogger("helixos")
    if getattr(logger, "_helix_configured", False):
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(ContextFilter())
    if os.getenv("HELIX_LOG_FORMAT", "json").lower() == "text":
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s", defaults={"request_id": "-"})
        )
    else:
        handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(os.getenv("HELIX_LOG_LEVEL", "info").upper())
    logger.propagate = False
    logger._helix_configured = True  # type: ignore[attr-defined]


access_logger = logging.getLogger("helixos.access")


class RequestContextMiddleware:
    """Pure ASGI middleware (safe for streaming/SSE responses)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inbound = dict(scope["headers"]).get(REQUEST_ID_HEADER.lower().encode(), b"").decode("latin-1")
        request_id = inbound if _INBOUND_ID.match(inbound) else f"req_{uuid4().hex[:16]}"
        context: dict[str, Any] = {"request_id": request_id}
        token = _log_context.set(context)
        started = time.perf_counter()
        status = 500
        response_started = False

        async def send_with_id(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER.lower().encode(), request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            try:
                await self.app(scope, receive, send_with_id)
            except Exception:  # noqa: BLE001 - last-resort boundary
                access_logger.exception("unhandled exception")
                if response_started:
                    raise
                status = 500
                body = json.dumps(
                    {
                        "error": {
                            "code": "internal_error",
                            "message": "Internal server error",
                            "details": {},
                            "request_id": request_id,
                        }
                    }
                ).encode()
                await send_with_id(
                    {
                        "type": "http.response.start",
                        "status": 500,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    }
                )
                await send_with_id({"type": "http.response.body", "body": body})
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            path = scope.get("path", "")
            level = logging.DEBUG if path == "/health" else logging.INFO
            access_logger.log(
                level,
                "request",
                extra={
                    "method": scope.get("method"),
                    "path": path,  # query string deliberately omitted
                    "status": status,
                    "duration_ms": duration_ms,
                },
            )
            _log_context.reset(token)
