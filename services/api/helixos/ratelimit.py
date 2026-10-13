"""Request rate limiting and request-size limits.

Token buckets held in process memory. That is correct while the API runs as a
single instance (it is capped at one: agent sessions are in-memory too); scaling
out needs a shared store behind :class:`RateLimiter`.

What is limited, and by whom:

* authenticated requests, per user (reads and a stricter bucket for writes);
* named expensive actions (AI runs, MCP jobs, invite acceptance), per user and,
  for AI, per organization;
* failed authentication, per client IP. Valid tokens are never blocked by it:
  many users can share one proxy address, so it only slows credential guessing.
"""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from helixos import limits
from helixos.errors import api_error
from helixos.observability import current_request_id

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class Decision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int  # whole seconds until one more request would be allowed


class RateLimiter:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 50_000,
    ) -> None:
        self._clock = clock
        self._max_keys = max_keys
        self._lock = threading.Lock()
        # key -> (tokens, last_seen, window); insertion order doubles as LRU order
        self._buckets: OrderedDict[str, tuple[float, float, float]] = OrderedDict()

    def hit(
        self, scope: str, key: str, limit: int, per_seconds: float = 60.0
    ) -> Decision:
        """Spend one token from ``scope:key``'s bucket (``limit`` per ``per_seconds``)."""
        rate = limit / per_seconds
        name = f"{scope}:{key}"
        with self._lock:
            now = self._clock()
            tokens, last, _ = self._buckets.pop(name, (float(limit), now, per_seconds))
            tokens = min(float(limit), tokens + (now - last) * rate)
            allowed = tokens >= 1.0
            if allowed:
                tokens -= 1.0
            self._buckets[name] = (tokens, now, per_seconds)
            if len(self._buckets) > self._max_keys:
                self._trim(now)
            retry = 0 if allowed else math.ceil((1.0 - tokens) / rate)
            return Decision(allowed, limit, int(tokens), retry)

    def _trim(self, now: float) -> None:
        """Drop buckets that have refilled to full (idle), then the oldest if still over."""
        idle = [
            name
            for name, (_tokens, last, window) in self._buckets.items()
            if now - last >= window
        ]
        for name in idle:
            del self._buckets[name]
        while len(self._buckets) > self._max_keys:
            self._buckets.popitem(last=False)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


rate_limiter = RateLimiter()


def _too_many(scope: str, decision: Decision, message: str):
    return api_error(
        status_code=429,
        code="rate_limited",
        message=message,
        details={
            "scope": scope,
            "limit": decision.limit,
            "retry_after_seconds": decision.retry_after,
        },
        headers={
            "Retry-After": str(max(1, decision.retry_after)),
            "X-RateLimit-Limit": str(decision.limit),
            "X-RateLimit-Remaining": "0",
        },
    )


def enforce(
    scope: str,
    key: str,
    limit: int,
    per_seconds: float = 60.0,
    *,
    message: str | None = None,
) -> None:
    """Raise 429 when ``key`` has exceeded ``limit`` per ``per_seconds`` in ``scope``."""
    if not limits.rate_limit_settings().enabled:
        return
    decision = rate_limiter.hit(scope, key, limit, per_seconds)
    if not decision.allowed:
        raise _too_many(
            scope,
            decision,
            message
            or f"Too many requests. Try again in {max(1, decision.retry_after)} seconds.",
        )


def enforce_actor(actor, method: str) -> None:
    """The default limits every authenticated request passes through."""
    settings = limits.rate_limit_settings()
    if not settings.enabled:
        return
    enforce("actor", actor.subject, settings.actor_per_minute)
    if method not in SAFE_METHODS:
        enforce(
            "write",
            actor.subject,
            settings.write_per_minute,
            message="Too many changes in a short time. Slow down and retry shortly.",
        )


def client_ip(request: Request) -> str:
    """The immediate caller's address.

    Behind ``HELIX_TRUSTED_PROXY_HOPS`` proxies, X-Forwarded-For is trusted only
    from the right: each trusted proxy appends the address it saw, so entries a
    client supplied sit to the left and cannot be used to pick a bucket.
    """
    hops = limits.rate_limit_settings().trusted_proxy_hops
    if hops:
        forwarded = [
            part.strip()
            for part in request.headers.get("x-forwarded-for", "").split(",")
            if part.strip()
        ]
        if len(forwarded) >= hops:
            return forwarded[-hops]
    return request.client.host if request.client else "unknown"


def record_auth_failure(request: Request) -> None:
    """Count a rejected credential; once an address guesses too much, answer 429."""
    settings = limits.rate_limit_settings()
    if not settings.enabled:
        return
    decision = rate_limiter.hit(
        "auth_failure", client_ip(request), settings.auth_failures_per_minute
    )
    if not decision.allowed:
        raise _too_many(
            "auth_failure",
            decision,
            f"Too many failed sign-in attempts. Try again in {max(1, decision.retry_after)} seconds.",
        )


def _payload_too_large(limit: int):
    return api_error(
        status_code=413,
        code="payload_too_large",
        message=f"Request body exceeds the {limit} byte limit",
        details={"limit_bytes": limit},
    )


class MaxBodySizeMiddleware:
    """Reject request bodies over ``HELIX_MAX_BODY_BYTES`` (413), declared or streamed."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = limits.rate_limit_settings().max_body_bytes
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            # Refuse without reading a byte of it.
            await _respond(_payload_too_large(limit), scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # An HTTP error, not a bespoke one: FastAPI turns any other
                    # exception raised while reading a body into a generic 400.
                    raise _payload_too_large(limit)
            return message

        await self.app(scope, limited_receive, send)


async def _respond(error, scope: Scope, receive: Receive, send: Send) -> None:
    payload = dict(error.detail)
    request_id = current_request_id()
    if request_id is not None:
        payload["request_id"] = request_id
    await JSONResponse({"error": payload}, status_code=error.status_code)(
        scope, receive, send
    )
