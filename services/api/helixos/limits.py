"""Request-rate and AI-spend limits: settings read from the environment.

Everything is optional with safe defaults, except that a hosted deployment with a
paid AI provider must state its spending caps and token prices (see
``config.validate_runtime_config``): a cap that silently does not exist is the
failure this module is for.
"""

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from helixos import config

MIB = 1024 * 1024


def _read_int(name: str, default: int, low: int, high: int, problems: list[str]) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        problems.append(f"{name} must be an integer, got {raw!r}")
        return default
    if not low <= value <= high:
        problems.append(f"{name} must be between {low} and {high}, got {value}")
        return default
    return value


def _read_usd(name: str, problems: list[str]) -> Decimal | None:
    """A non-negative USD amount, or None when unset."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        problems.append(f"{name} must be a number of US dollars, got {raw!r}")
        return None
    if not value.is_finite() or value < 0:
        problems.append(f"{name} must be zero or more, got {raw!r}")
        return None
    return value


def _micros(usd: Decimal | None) -> int | None:
    return None if usd is None else int(usd * 1_000_000)


# --------------------------------------------------------------------------- #
# Request rate limits
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RateLimitSettings:
    enabled: bool
    actor_per_minute: int
    write_per_minute: int
    ai_run_actor_per_minute: int
    ai_run_org_per_minute: int
    ai_session_per_minute: int
    mcp_job_per_minute: int
    invite_accept_per_hour: int
    auth_failures_per_minute: int
    trusted_proxy_hops: int
    max_body_bytes: int


def rate_limit_settings_and_problems() -> tuple[RateLimitSettings, list[str]]:
    problems: list[str] = []
    try:
        explicit = config._flag("HELIX_RATE_LIMIT_ENABLED")
    except config.ConfigError as error:
        problems.append(str(error))
        explicit = None
    enabled = explicit if explicit is not None else config.is_hosted()

    settings = RateLimitSettings(
        enabled=enabled,
        actor_per_minute=_read_int(
            "HELIX_RATE_LIMIT_ACTOR_PER_MINUTE", 600, 1, 100_000, problems
        ),
        write_per_minute=_read_int(
            "HELIX_RATE_LIMIT_WRITE_PER_MINUTE", 120, 1, 100_000, problems
        ),
        ai_run_actor_per_minute=_read_int(
            "HELIX_RATE_LIMIT_AI_RUN_PER_MINUTE", 6, 1, 1_000, problems
        ),
        ai_run_org_per_minute=_read_int(
            "HELIX_RATE_LIMIT_AI_RUN_ORG_PER_MINUTE", 30, 1, 10_000, problems
        ),
        ai_session_per_minute=_read_int(
            "HELIX_RATE_LIMIT_AI_SESSION_PER_MINUTE", 20, 1, 1_000, problems
        ),
        mcp_job_per_minute=_read_int(
            "HELIX_RATE_LIMIT_MCP_JOB_PER_MINUTE", 30, 1, 10_000, problems
        ),
        invite_accept_per_hour=_read_int(
            "HELIX_RATE_LIMIT_INVITE_ACCEPT_PER_HOUR", 30, 1, 10_000, problems
        ),
        auth_failures_per_minute=_read_int(
            "HELIX_RATE_LIMIT_AUTH_FAILURES_PER_MINUTE", 20, 1, 10_000, problems
        ),
        trusted_proxy_hops=_read_int("HELIX_TRUSTED_PROXY_HOPS", 0, 0, 5, problems),
        max_body_bytes=_read_int(
            "HELIX_MAX_BODY_BYTES", 2 * MIB, 1024, 64 * MIB, problems
        ),
    )
    return settings, problems


def rate_limit_settings() -> RateLimitSettings:
    settings, problems = rate_limit_settings_and_problems()
    if problems:
        raise config.ConfigError("; ".join(problems))
    return settings


# --------------------------------------------------------------------------- #
# AI per-run limits, prices and spend caps
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AiLimitSettings:
    max_output_tokens: int
    max_input_chars: int
    run_timeout_seconds: int
    max_concurrent_runs_per_user: int
    # USD per million tokens == micro-USD per token.
    price_input: Decimal
    price_output: Decimal
    global_monthly_micros: int | None
    org_daily_micros: int | None
    org_monthly_micros: int | None
    user_daily_micros: int | None

    @property
    def priced(self) -> bool:
        return self.price_input > 0 and self.price_output > 0

    @property
    def has_hard_caps(self) -> bool:
        """The two caps a paid provider must not run without."""
        return (
            self.global_monthly_micros is not None and self.org_daily_micros is not None
        )


def ai_limit_settings_and_problems() -> tuple[AiLimitSettings, list[str]]:
    problems: list[str] = []
    price_input = _read_usd("HELIX_AI_PRICE_INPUT_USD_PER_MTOK", problems)
    price_output = _read_usd("HELIX_AI_PRICE_OUTPUT_USD_PER_MTOK", problems)
    settings = AiLimitSettings(
        max_output_tokens=_read_int(
            "HELIX_AI_MAX_OUTPUT_TOKENS", 1024, 16, 32_768, problems
        ),
        max_input_chars=_read_int(
            "HELIX_AI_MAX_INPUT_CHARS", 8000, 100, 200_000, problems
        ),
        run_timeout_seconds=_read_int(
            "HELIX_AI_RUN_TIMEOUT_SECONDS", 120, 5, 3_600, problems
        ),
        # 0 = unlimited. On by default only when hosted, so local use and the
        # parallel-run evals are not throttled.
        max_concurrent_runs_per_user=_read_int(
            "HELIX_AI_MAX_CONCURRENT_RUNS_PER_USER",
            2 if config.is_hosted() else 0,
            0,
            50,
            problems,
        ),
        price_input=price_input or Decimal(0),
        price_output=price_output or Decimal(0),
        global_monthly_micros=_micros(
            _read_usd("HELIX_AI_BUDGET_GLOBAL_MONTHLY_USD", problems)
        ),
        org_daily_micros=_micros(_read_usd("HELIX_AI_BUDGET_ORG_DAILY_USD", problems)),
        org_monthly_micros=_micros(
            _read_usd("HELIX_AI_BUDGET_ORG_MONTHLY_USD", problems)
        ),
        user_daily_micros=_micros(
            _read_usd("HELIX_AI_BUDGET_USER_DAILY_USD", problems)
        ),
    )
    return settings, problems


def ai_limit_settings() -> AiLimitSettings:
    settings, problems = ai_limit_settings_and_problems()
    if problems:
        raise config.ConfigError("; ".join(problems))
    return settings
