"""Deployment environment and startup validation.

``HELIX_ENV`` selects the posture: ``development`` (default, local and desktop
sidecar), ``staging`` or ``production``. Hosted environments (staging and
production) fail closed: the process refuses to start on unsafe configuration
instead of serving with demo tokens, wildcard CORS or throwaway storage.
"""

import logging
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from helixos.ai.settings import AISettings
from helixos.db.settings import DatabaseSettings

logger = logging.getLogger("helixos.config")

DEVELOPMENT = "development"
STAGING = "staging"
PRODUCTION = "production"
ENVIRONMENTS = (DEVELOPMENT, STAGING, PRODUCTION)


class ConfigError(RuntimeError):
    """Raised when the process environment is unsafe or malformed."""


def _flag(name: str) -> bool | None:
    """Read a ``1``/``0`` flag; ``None`` when unset. Anything else is an error."""
    value = os.getenv(name, "").strip()
    if value == "":
        return None
    if value not in ("0", "1"):
        raise ConfigError(f"{name} must be 0 or 1, got {value!r}")
    return value == "1"


def environment() -> str:
    value = os.getenv("HELIX_ENV", DEVELOPMENT).strip().lower() or DEVELOPMENT
    if value not in ENVIRONMENTS:
        raise ConfigError(
            f"HELIX_ENV must be one of {', '.join(ENVIRONMENTS)}, got {value!r}"
        )
    return value


def is_hosted() -> bool:
    return environment() != DEVELOPMENT


def demo_tokens_enabled() -> bool:
    """Whether the documented demo bearer tokens authenticate.

    On in development, opt-in (``HELIX_ENABLE_DEMO_TOKENS=1``) in staging so a
    pre-launch environment is usable before real identity exists, never in
    production.
    """
    env = environment()
    if env == PRODUCTION:
        return False
    explicit = _flag("HELIX_ENABLE_DEMO_TOKENS")
    if explicit is not None:
        return explicit
    return env == DEVELOPMENT


def unverified_jwt_enabled() -> bool:
    """Unsigned-JWT decoding for local dev against a mock IdP; never when hosted."""
    return not is_hosted() and os.getenv("HELIX_ALLOW_UNVERIFIED_JWT") == "1"


def docs_enabled() -> bool:
    """Whether /docs, /redoc and /openapi.json are served."""
    explicit = _flag("HELIX_ENABLE_DOCS")
    if explicit is not None:
        return explicit
    return environment() != PRODUCTION


def _parse_origins(raw: str) -> tuple[tuple[str, ...], list[str]]:
    origins: list[str] = []
    problems: list[str] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if item == "*":
            problems.append(
                "ALLOWED_ORIGINS must not contain '*'; list explicit origins"
            )
            continue
        parts = urlsplit(item)
        if (
            parts.scheme not in ("http", "https")
            or not parts.hostname
            or parts.path.strip("/")
            or parts.query
            or parts.fragment
            or parts.username
        ):
            problems.append(
                f"ALLOWED_ORIGINS entry {item!r} is not an origin "
                "(expected scheme://host[:port], no path)"
            )
            continue
        origins.append(f"{parts.scheme}://{parts.netloc}".lower())
    return tuple(dict.fromkeys(origins)), problems


def allowed_origins() -> tuple[str, ...]:
    """Explicit CORS origins from ``ALLOWED_ORIGINS`` (comma-separated)."""
    origins, problems = _parse_origins(os.getenv("ALLOWED_ORIGINS", ""))
    if problems:
        raise ConfigError("; ".join(problems))
    return origins


ASYMMETRIC_ALGORITHMS = frozenset(
    {
        "RS256",
        "RS384",
        "RS512",
        "ES256",
        "ES384",
        "ES512",
        "PS256",
        "PS384",
        "PS512",
        "EdDSA",
    }
)
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass(frozen=True)
class OidcSettings:
    """Bearer-token verification against an OpenID Connect provider."""

    issuer: str
    audience: str
    jwks_url: str | None
    algorithms: tuple[str, ...]
    leeway_seconds: int
    email_claim: str
    name_claim: str


def _oidc_problems() -> tuple[OidcSettings | None, list[str]]:
    issuer = os.getenv("HELIX_OIDC_ISSUER", "").strip()
    if not issuer:
        return None, []
    problems: list[str] = []
    audience = os.getenv("HELIX_OIDC_AUDIENCE", "").strip()
    if not audience:
        problems.append(
            "HELIX_OIDC_AUDIENCE is required with HELIX_OIDC_ISSUER "
            "(the API identifier or client id tokens are issued for)"
        )
    jwks_url = os.getenv("HELIX_OIDC_JWKS_URL", "").strip() or None
    for name, url in (("HELIX_OIDC_ISSUER", issuer), ("HELIX_OIDC_JWKS_URL", jwks_url)):
        if url is None:
            continue
        parts = urlsplit(url)
        local = parts.hostname in _LOCAL_HOSTS
        if parts.scheme != "https" and not (parts.scheme == "http" and local):
            problems.append(f"{name} must be an https URL (http only for localhost)")
    algorithms = tuple(
        item.strip()
        for item in os.getenv("HELIX_OIDC_ALGORITHMS", "RS256,ES256").split(",")
        if item.strip()
    )
    unsupported = [item for item in algorithms if item not in ASYMMETRIC_ALGORITHMS]
    if unsupported or not algorithms:
        problems.append(
            "HELIX_OIDC_ALGORITHMS must list asymmetric algorithms only "
            f"({', '.join(sorted(ASYMMETRIC_ALGORITHMS))}); got {unsupported or 'none'}"
        )
    try:
        leeway = int(os.getenv("HELIX_OIDC_LEEWAY_SECONDS", "30"))
        if not 0 <= leeway <= 300:
            raise ValueError
    except ValueError:
        problems.append("HELIX_OIDC_LEEWAY_SECONDS must be an integer from 0 to 300")
        leeway = 30
    if problems:
        return None, problems
    return (
        OidcSettings(
            issuer=issuer,
            audience=audience,
            jwks_url=jwks_url,
            algorithms=algorithms,
            leeway_seconds=leeway,
            email_claim=os.getenv("HELIX_OIDC_EMAIL_CLAIM", "email").strip() or "email",
            name_claim=os.getenv("HELIX_OIDC_NAME_CLAIM", "name").strip() or "name",
        ),
        [],
    )


def oidc_settings() -> OidcSettings | None:
    """OIDC configuration, or ``None`` when no issuer is set."""
    settings, problems = _oidc_problems()
    if problems:
        raise ConfigError("; ".join(problems))
    return settings


def validate_runtime_config(database: DatabaseSettings, ai: AISettings) -> None:
    """Raise :class:`ConfigError` listing every unsafe setting for this environment."""
    problems: list[str] = []

    try:
        env = environment()
    except ConfigError as error:
        raise ConfigError(f"Invalid HelixOS configuration:\n - {error}") from error

    for check in (demo_tokens_enabled, docs_enabled):
        try:
            check()
        except ConfigError as error:
            problems.append(str(error))

    origins, origin_problems = _parse_origins(os.getenv("ALLOWED_ORIGINS", ""))
    problems.extend(origin_problems)

    oidc, oidc_problems = _oidc_problems()
    problems.extend(oidc_problems)
    if (oidc is not None or oidc_problems) and database.backend == "memory":
        problems.append(
            "HELIX_OIDC_ISSUER needs HELIX_DATABASE_URL: users and memberships are stored there"
        )

    from helixos import limits  # imported here: limits depends on this module

    rate_settings, rate_problems = limits.rate_limit_settings_and_problems()
    ai_limits, ai_limit_problems = limits.ai_limit_settings_and_problems()
    problems.extend(rate_problems)
    problems.extend(ai_limit_problems)

    if env != DEVELOPMENT:
        if not rate_settings.enabled:
            problems.append(
                "HELIX_RATE_LIMIT_ENABLED=0 is not allowed when hosted: "
                "rate limiting must stay on"
            )
        if ai.effective_provider != "stub":
            # A paid provider without prices or caps has no spend ceiling at all.
            if not ai_limits.priced:
                problems.append(
                    "HELIX_AI_PRICE_INPUT_USD_PER_MTOK and HELIX_AI_PRICE_OUTPUT_USD_PER_MTOK "
                    "are required with a paid AI provider (spend caps need prices)"
                )
            if not ai_limits.has_hard_caps:
                problems.append(
                    "HELIX_AI_BUDGET_GLOBAL_MONTHLY_USD and HELIX_AI_BUDGET_ORG_DAILY_USD "
                    "are required with a paid AI provider"
                )
        if not origins and not origin_problems:
            problems.append("ALLOWED_ORIGINS is required (comma-separated web origins)")
        if os.getenv("HELIX_ALLOW_UNVERIFIED_JWT") == "1":
            problems.append(
                "HELIX_ALLOW_UNVERIFIED_JWT=1 accepts forged tokens; unset it"
            )
        if database.backend == "memory":
            problems.append(
                "HELIX_DATABASE_URL is required; the in-memory store loses data on restart"
            )

    if env == PRODUCTION:
        if oidc is None and not oidc_problems:
            problems.append(
                "HELIX_OIDC_ISSUER and HELIX_OIDC_AUDIENCE are required: "
                "production has no other way to authenticate"
            )
        if _flag_safe("HELIX_ENABLE_DEMO_TOKENS"):
            problems.append("HELIX_ENABLE_DEMO_TOKENS=1 is not allowed in production")
        insecure = [origin for origin in origins if not origin.startswith("https://")]
        if insecure:
            problems.append(
                f"ALLOWED_ORIGINS must use https in production: {', '.join(insecure)}"
            )
        if database.backend not in ("memory", "postgresql"):
            problems.append(
                "production requires PostgreSQL "
                "(HELIX_DATABASE_URL=postgresql+psycopg://...)"
            )
        if ai.provider not in ("openai", "vertex"):
            problems.append("HELIX_AI_PROVIDER must be openai or vertex in production")
        elif ai.effective_provider != ai.provider:
            problems.append(
                f"HELIX_AI_PROVIDER={ai.provider} is missing its credentials/project "
                "and would silently fall back to the stub"
            )

    if problems:
        raise ConfigError(
            f"Invalid HelixOS configuration (HELIX_ENV={env}):\n - "
            + "\n - ".join(problems)
        )

    if env != DEVELOPMENT:
        if ai.effective_provider == "stub":
            logger.warning("AI provider is the stub; agent runs return canned output")
        if demo_tokens_enabled():
            logger.warning("Demo bearer tokens are enabled in %s", env)
        if oidc is None:
            logger.warning(
                "No OIDC provider configured; only demo tokens can authenticate"
            )


def _flag_safe(name: str) -> bool:
    try:
        return bool(_flag(name))
    except ConfigError:
        return False
