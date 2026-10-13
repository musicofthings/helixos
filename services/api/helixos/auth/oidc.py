"""OIDC bearer-token verification (signature, issuer, audience, expiry).

Provider-agnostic: any OpenID Connect provider that publishes a JWKS works
(Auth0, Clerk, Google Identity Platform, Keycloak, Cognito, ...). Only
asymmetric algorithms from the configured allow-list are accepted, so ``none``
and HMAC-with-the-public-key downgrade attacks are impossible.
"""

import json
import logging
import threading
import time
import urllib.request
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import jwt

from helixos.config import OidcSettings

logger = logging.getLogger("helixos.auth.oidc")

MAX_TOKEN_LENGTH = 8192
_MAX_RESPONSE_BYTES = 1_000_000
_FETCH_TIMEOUT_SECONDS = 5

Fetch = Callable[[str], dict[str, Any]]


class OidcError(Exception):
    """A token was rejected. ``reason`` is for logs only, never sent to clients."""

    def __init__(self, reason: str, *, unavailable: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        # True when the provider could not be reached (retryable), not a bad token.
        self.unavailable = unavailable


def http_get_json(url: str) -> dict[str, Any]:
    if urlsplit(url).scheme not in ("http", "https"):
        raise OidcError("bad_url", unavailable=True)
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:  # noqa: S310
        body = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(body) > _MAX_RESPONSE_BYTES:
        raise ValueError("response too large")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


class OidcVerifier:
    def __init__(
        self,
        settings: OidcSettings,
        *,
        fetch: Fetch | None = None,
        clock: Callable[[], float] = time.monotonic,
        keys_ttl: float = 3600.0,
        min_refresh_interval: float = 30.0,
    ) -> None:
        self.settings = settings
        # Resolved per call so tests can substitute the module-level fetcher.
        self._fetch = fetch or (lambda url: http_get_json(url))
        self._clock = clock
        self._keys_ttl = keys_ttl
        self._min_refresh = min_refresh_interval
        self._lock = threading.Lock()
        self._jwks_url = settings.jwks_url
        self._keys: dict[str | None, jwt.PyJWK] = {}
        self._fetched_at: float | None = None
        self._attempted_at: float | None = None

    # ------------------------------------------------------------------ #
    def verify(self, token: str) -> dict[str, Any]:
        """Return the verified claims or raise :class:`OidcError`."""
        if len(token) > MAX_TOKEN_LENGTH:
            raise OidcError("token_too_large")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise OidcError("malformed") from None
        algorithm = header.get("alg")
        if algorithm not in self.settings.algorithms:
            raise OidcError("algorithm_not_allowed")

        key = self._signing_key(header.get("kid"))
        try:
            claims = jwt.decode(
                token,
                key.key,
                algorithms=[algorithm],
                audience=self.settings.audience,
                issuer=self.settings.issuer,
                leeway=self.settings.leeway_seconds,
                options={"require": ["exp", "iss", "sub", "aud"]},
            )
        except jwt.ExpiredSignatureError:
            raise OidcError("expired") from None
        except jwt.PyJWTError as error:
            raise OidcError(f"invalid_{type(error).__name__}") from None
        if not isinstance(claims.get("sub"), str) or not claims["sub"]:
            raise OidcError("invalid_subject")
        return claims

    # ------------------------------------------------------------------ #
    def _signing_key(self, kid: str | None) -> jwt.PyJWK:
        with self._lock:
            now = self._clock()
            stale = self._fetched_at is None or now - self._fetched_at > self._keys_ttl
            if not stale and self._has_key(kid):
                return self._pick(kid)
            # Unknown kid or expired cache: refetch, but never more than once per
            # interval so forged kids cannot turn this API into a DoS on the IdP.
            if (
                self._attempted_at is None
                or now - self._attempted_at >= self._min_refresh
            ):
                self._refresh(now)
            if self._has_key(kid):
                return self._pick(kid)
            if not self._keys:
                raise OidcError("jwks_unavailable", unavailable=True)
            raise OidcError("unknown_key")

    def _has_key(self, kid: str | None) -> bool:
        if kid is None:
            return len(self._keys) == 1
        return kid in self._keys

    def _pick(self, kid: str | None) -> jwt.PyJWK:
        return next(iter(self._keys.values())) if kid is None else self._keys[kid]

    def _refresh(self, now: float) -> None:
        self._attempted_at = now
        try:
            document = self._fetch(self._resolve_jwks_url())
            keys: dict[str | None, jwt.PyJWK] = {}
            for entry in document.get("keys", []):
                if not isinstance(entry, dict) or entry.get("use", "sig") != "sig":
                    continue
                try:
                    key = jwt.PyJWK.from_dict(entry)
                except jwt.PyJWTError:
                    continue
                keys[entry.get("kid")] = key
        except OidcError:
            raise
        except Exception as error:  # network, TLS, JSON: keep serving cached keys
            logger.warning("jwks refresh failed", extra={"error": type(error).__name__})
            return
        if keys:
            self._keys = keys
            self._fetched_at = now

    def _resolve_jwks_url(self) -> str:
        if self._jwks_url:
            return self._jwks_url
        base = self.settings.issuer.rstrip("/")
        document = self._fetch(f"{base}/.well-known/openid-configuration")
        if document.get("issuer") != self.settings.issuer:
            raise ValueError("discovery issuer mismatch")
        url = document.get("jwks_uri")
        if not isinstance(url, str) or not url:
            raise ValueError("discovery document has no jwks_uri")
        self._jwks_url = url
        return url
