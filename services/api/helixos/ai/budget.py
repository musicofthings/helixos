"""AI spend accounting and caps.

Every agent run follows the same three steps:

1. **Reserve** (before anything is streamed): estimate the run's worst-case cost
   (the prompt plus the maximum output allowed) and refuse it if that would push
   any applicable cap over the line. The estimate is held against the caps so
   runs started at the same moment cannot all slip under them together.
2. **Run** with a hard output-token ceiling.
3. **Settle**: record what was actually consumed (provider-reported tokens, or an
   estimate when the provider reports none) in the persistent ``ai_usage``
   ledger, then release the hold.

Caps are sums over the ledger in UTC calendar windows. Reservations live in
process memory, which is correct for the single-instance deployment; running
several instances would need them in the database too.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Protocol
from uuid import uuid4

from sqlalchemy import func, select

from helixos import limits
from helixos.ai.orm import AiUsageORM
from helixos.db.session import session_scope
from helixos.db.settings import DatabaseSettings, get_database_settings
from helixos.errors import api_error

logger = logging.getLogger("helixos.ai.budget")

# Characters per token used when a count must be estimated. Deliberately
# pessimistic (English text is nearer 4; code and sequences are worse): it is
# better to over-count spend than to under-count it.
CHARS_PER_TOKEN = 3
# A reservation outlives its run's timeout by this much before it is reclaimed,
# so a run abandoned before it started cannot hold budget forever.
RESERVATION_GRACE_SECONDS = 30


def estimate_tokens(characters: int) -> int:
    return math.ceil(max(0, characters) / CHARS_PER_TOKEN)


def cost_micros(
    input_tokens: int, output_tokens: int, settings: limits.AiLimitSettings
) -> int:
    """Cost in millionths of a dollar. Prices are USD per million tokens, which is
    the same number as micro-USD per token."""
    cost = (
        Decimal(input_tokens) * settings.price_input
        + Decimal(output_tokens) * settings.price_output
    )
    return math.ceil(cost)


def usd(micros: int) -> str:
    """Dollars as a fixed six-decimal string (micro-dollar precision)."""
    return format(
        (Decimal(micros) / Decimal(1_000_000)).quantize(Decimal("0.000001")), "f"
    )


@dataclass(frozen=True)
class UsageRecord:
    id: str
    organization_id: str
    user_id: str
    run_id: str
    provider: str
    model: str | None
    input_tokens: int
    output_tokens: int
    cost_micros: int
    estimated: bool
    status: str
    created_at: datetime


class UsageStore(Protocol):
    def add(self, record: UsageRecord) -> None: ...

    def spent(
        self,
        since: datetime,
        *,
        organization_id: str | None = None,
        user_id: str | None = None,
    ) -> int: ...


class MemoryUsageStore:
    """Process-local ledger for runs without a database (development)."""

    def __init__(self, max_records: int = 50_000) -> None:
        self._records: deque[UsageRecord] = deque(maxlen=max_records)
        self._lock = threading.Lock()

    def add(self, record: UsageRecord) -> None:
        with self._lock:
            self._records.append(record)

    def spent(
        self,
        since: datetime,
        *,
        organization_id: str | None = None,
        user_id: str | None = None,
    ) -> int:
        with self._lock:
            return sum(
                r.cost_micros
                for r in self._records
                if r.created_at >= since
                and (organization_id is None or r.organization_id == organization_id)
                and (user_id is None or r.user_id == user_id)
            )


class SqlUsageStore:
    def add(self, record: UsageRecord) -> None:
        with session_scope() as session:
            session.add(AiUsageORM(**record.__dict__))

    def spent(
        self,
        since: datetime,
        *,
        organization_id: str | None = None,
        user_id: str | None = None,
    ) -> int:
        query = select(func.coalesce(func.sum(AiUsageORM.cost_micros), 0)).where(
            AiUsageORM.created_at >= since
        )
        if organization_id is not None:
            query = query.where(AiUsageORM.organization_id == organization_id)
        if user_id is not None:
            query = query.where(AiUsageORM.user_id == user_id)
        with session_scope() as session:
            return int(session.scalar(query) or 0)


def build_usage_store(settings: DatabaseSettings | None = None) -> UsageStore:
    resolved = settings or get_database_settings()
    return SqlUsageStore() if resolved.is_configured else MemoryUsageStore()


@dataclass
class Reservation:
    id: str
    organization_id: str
    user_id: str
    cost_micros: int
    expires_at: float  # monotonic seconds
    settled: bool = False


@dataclass(frozen=True)
class Window:
    since: datetime
    resets_at: datetime


def day_window(now: datetime) -> Window:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return Window(start, start + timedelta(days=1))


def month_window(now: datetime) -> Window:
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    following = (start + timedelta(days=32)).replace(day=1)
    return Window(start, following)


_MESSAGES = {
    "global_monthly": "The platform's monthly AI budget has been reached; AI features are unavailable until it resets.",
    "organization_monthly": "Your organization's monthly AI budget has been reached. It resets at the start of next month (UTC).",
    "organization_daily": "Your organization's daily AI budget has been reached. It resets at midnight UTC.",
    "user_daily": "You have reached your daily AI limit. It resets at midnight UTC.",
}


@dataclass
class BudgetService:
    store: UsageStore = field(default_factory=MemoryUsageStore)
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    monotonic: Callable[[], float] = time.monotonic
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _reservations: dict[str, Reservation] = field(default_factory=dict)

    def use_store(self, store: UsageStore) -> None:
        self.store = store

    # ------------------------------------------------------------------ #
    def reserve(
        self, *, organization_id: str, user_id: str, prompt_chars: int
    ) -> Reservation:
        """Hold worst-case spend for a run, or raise 429 if a cap would be exceeded."""
        settings = limits.ai_limit_settings()
        estimate = cost_micros(
            estimate_tokens(prompt_chars), settings.max_output_tokens, settings
        )
        now = self.clock()
        day, month = day_window(now), month_window(now)
        checks = (
            ("global_monthly", settings.global_monthly_micros, month, None, None),
            (
                "organization_monthly",
                settings.org_monthly_micros,
                month,
                organization_id,
                None,
            ),
            (
                "organization_daily",
                settings.org_daily_micros,
                day,
                organization_id,
                None,
            ),
            ("user_daily", settings.user_daily_micros, day, None, user_id),
        )

        with self._lock:
            self._expire()
            running = [r for r in self._reservations.values() if r.user_id == user_id]
            limit = settings.max_concurrent_runs_per_user
            if limit and len(running) >= limit:
                raise api_error(
                    status_code=429,
                    code="ai_concurrency_limit",
                    message=f"You already have {len(running)} agent runs in progress. Wait for one to finish.",
                    details={"scope": "user_concurrency", "limit": limit},
                    headers={"Retry-After": "5"},
                )

            for scope, cap, window, org, user in checks:
                if cap is None:
                    continue
                spent = self.store.spent(
                    window.since, organization_id=org, user_id=user
                )
                held = sum(
                    r.cost_micros
                    for r in self._reservations.values()
                    if (org is None or r.organization_id == org)
                    and (user is None or r.user_id == user)
                )
                if spent + held + estimate > cap:
                    retry = max(1, int((window.resets_at - now).total_seconds()))
                    logger.warning(
                        "ai budget exceeded",
                        extra={
                            "scope": scope,
                            "organization_id": organization_id,
                            "spent_usd": usd(spent),
                            "held_usd": usd(held),
                            "cap_usd": usd(cap),
                        },
                    )
                    raise api_error(
                        status_code=429,
                        code="ai_budget_exceeded",
                        message=_MESSAGES[scope],
                        # Scope and reset time only: dollar figures are for admins.
                        details={
                            "scope": scope,
                            "resets_at": window.resets_at.isoformat(),
                            "retry_after_seconds": retry,
                        },
                        headers={"Retry-After": str(retry)},
                    )

            reservation = Reservation(
                id=f"res_{uuid4().hex}",
                organization_id=organization_id,
                user_id=user_id,
                cost_micros=estimate,
                expires_at=self.monotonic()
                + settings.run_timeout_seconds
                + RESERVATION_GRACE_SECONDS,
            )
            self._reservations[reservation.id] = reservation
            return reservation

    def record(
        self,
        reservation: Reservation,
        *,
        run_id: str,
        provider: str,
        model: str | None,
        input_tokens: int,
        output_tokens: int,
        estimated: bool,
        status: str,
    ) -> UsageRecord:
        """Write what the run really consumed to the ledger.

        Does not release the hold: the caller releases it once the surrounding
        transaction has committed, so a retried transaction cannot lose the spend.
        """
        record = UsageRecord(
            id=f"use_{uuid4().hex}",
            organization_id=reservation.organization_id,
            user_id=reservation.user_id,
            run_id=run_id,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_micros=cost_micros(
                input_tokens, output_tokens, limits.ai_limit_settings()
            ),
            estimated=estimated,
            status=status,
            created_at=self.clock(),
        )
        self.store.add(record)
        return record

    def release(self, reservation: Reservation) -> None:
        """Drop a hold without recording spend (the run never reached the provider)."""
        with self._lock:
            reservation.settled = True
            self._reservations.pop(reservation.id, None)

    # ------------------------------------------------------------------ #
    def summary(self, organization_id: str, user_id: str) -> dict[str, object]:
        settings = limits.ai_limit_settings()
        now = self.clock()
        day, month = day_window(now), month_window(now)

        def line(window: Window, cap: int | None, **scope: str) -> dict[str, object]:
            spent = self.store.spent(window.since, **scope)
            return {
                "spent_usd": usd(spent),
                "cap_usd": usd(cap) if cap is not None else None,
                "remaining_usd": usd(max(0, cap - spent)) if cap is not None else None,
                "resets_at": window.resets_at.isoformat(),
            }

        return {
            "organization_id": organization_id,
            "currency": "USD",
            "organization_day": line(
                day, settings.org_daily_micros, organization_id=organization_id
            ),
            "organization_month": line(
                month, settings.org_monthly_micros, organization_id=organization_id
            ),
            "you_day": line(day, settings.user_daily_micros, user_id=user_id),
            "max_output_tokens_per_run": settings.max_output_tokens,
        }

    def _expire(self) -> None:
        cutoff = self.monotonic()
        for key in [k for k, r in self._reservations.items() if r.expires_at <= cutoff]:
            self._reservations.pop(key).settled = True


budget_service = BudgetService()
