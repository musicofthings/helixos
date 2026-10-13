"""AI spend caps: pricing, windows, reservations, and settlement on every exit path."""

import asyncio
import dataclasses
import json
from datetime import datetime, timezone

import pytest
from backends import ELN_CLIENT_FIXTURES
from fastapi import HTTPException

from helixos import limits
from helixos.ai import budget as budget_module
from helixos.ai.budget import (
    BudgetService,
    MemoryUsageStore,
    budget_service,
    cost_micros,
    day_window,
    estimate_tokens,
    month_window,
)
from helixos.ai.providers import Usage
from helixos.ai.service import AgentService
from helixos.auth.service import DEMO_TOKENS

SCIENTIST = {"Authorization": "Bearer org-demo-token"}
ADMIN = {"Authorization": "Bearer demo-admin-token"}
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)

ENV_NAMES = (
    "HELIX_AI_PRICE_INPUT_USD_PER_MTOK",
    "HELIX_AI_PRICE_OUTPUT_USD_PER_MTOK",
    "HELIX_AI_BUDGET_GLOBAL_MONTHLY_USD",
    "HELIX_AI_BUDGET_ORG_DAILY_USD",
    "HELIX_AI_BUDGET_ORG_MONTHLY_USD",
    "HELIX_AI_BUDGET_USER_DAILY_USD",
    "HELIX_AI_MAX_OUTPUT_TOKENS",
    "HELIX_AI_MAX_INPUT_CHARS",
    "HELIX_AI_RUN_TIMEOUT_SECONDS",
    "HELIX_AI_MAX_CONCURRENT_RUNS_PER_USER",
)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    budget_service.use_store(MemoryUsageStore())
    budget_service._reservations.clear()
    yield
    budget_service._reservations.clear()


def priced(
    monkeypatch, price: str = "1000", max_output: str = "16", **caps: str
) -> None:
    """Price tokens at ``price`` USD per million (== micro-USD per token) and set caps."""
    monkeypatch.setenv("HELIX_AI_PRICE_INPUT_USD_PER_MTOK", price)
    monkeypatch.setenv("HELIX_AI_PRICE_OUTPUT_USD_PER_MTOK", price)
    monkeypatch.setenv("HELIX_AI_MAX_OUTPUT_TOKENS", max_output)
    for name, value in caps.items():
        monkeypatch.setenv(f"HELIX_AI_BUDGET_{name.upper()}_USD", value)


class FakeClock:
    def __init__(self, start: datetime = NOW) -> None:
        self.now = start
        self.mono = 0.0

    def __call__(self) -> datetime:
        return self.now


def make_service(
    clock: FakeClock | None = None,
) -> tuple[BudgetService, MemoryUsageStore, FakeClock]:
    clock = clock or FakeClock()
    store = MemoryUsageStore()
    return (
        BudgetService(store=store, clock=clock, monotonic=lambda: clock.mono),
        store,
        clock,
    )


def spend(
    service: BudgetService, org: str, user: str, micros: int, at: datetime | None = None
):
    reservation = service.reserve(organization_id=org, user_id=user, prompt_chars=0)
    record = service.record(
        reservation,
        run_id="run_x",
        provider="openai",
        model="m",
        input_tokens=micros,  # 1 micro-USD per token at the test price of 1
        output_tokens=0,
        estimated=False,
        status="completed",
    )
    service.release(reservation)
    return record


# --------------------------------------------------------------------------- #
# Pricing and windows
# --------------------------------------------------------------------------- #
def test_cost_is_priced_per_million_tokens_and_rounds_up(monkeypatch) -> None:
    monkeypatch.setenv("HELIX_AI_PRICE_INPUT_USD_PER_MTOK", "3")
    monkeypatch.setenv("HELIX_AI_PRICE_OUTPUT_USD_PER_MTOK", "15")
    settings = limits.ai_limit_settings()
    assert cost_micros(1_000_000, 0, settings) == 3_000_000  # $3
    assert cost_micros(1000, 500, settings) == 3000 + 7500
    monkeypatch.setenv("HELIX_AI_PRICE_INPUT_USD_PER_MTOK", "0.15")
    assert (
        cost_micros(1, 0, limits.ai_limit_settings()) == 1
    )  # never rounds spend down to zero


def test_token_estimates_err_on_the_high_side() -> None:
    assert [estimate_tokens(n) for n in (0, 1, 3, 4, 300)] == [0, 1, 1, 2, 100]


def test_windows_are_utc_calendar_days_and_months() -> None:
    day = day_window(datetime(2026, 12, 31, 15, 30, tzinfo=timezone.utc))
    assert (day.since.isoformat(), day.resets_at.isoformat()) == (
        "2026-12-31T00:00:00+00:00",
        "2027-01-01T00:00:00+00:00",
    )
    month = month_window(datetime(2026, 12, 31, 15, 30, tzinfo=timezone.utc))
    assert month.resets_at.isoformat() == "2027-01-01T00:00:00+00:00"
    assert month_window(datetime(2028, 2, 10, tzinfo=timezone.utc)).resets_at.month == 3


# --------------------------------------------------------------------------- #
# Caps
# --------------------------------------------------------------------------- #
def test_runs_are_admitted_until_the_cap_would_be_crossed(monkeypatch) -> None:
    priced(monkeypatch, price="1", org_daily="0.001")  # 1000 micro-USD
    service, _store, _clock = make_service()
    spend(service, "org_a", "u1", 900)

    with pytest.raises(HTTPException) as refused:
        service.reserve(
            organization_id="org_a", user_id="u1", prompt_chars=300
        )  # ~116 micro-USD
    error = refused.value
    assert error.status_code == 429 and error.detail["code"] == "ai_budget_exceeded"
    assert error.detail["details"]["scope"] == "organization_daily"
    assert int(error.headers["Retry-After"]) == 12 * 3600  # until midnight UTC
    assert (
        "usd" not in json.dumps(error.detail).lower()
    )  # dollar figures are for admins only

    # A small prompt still fits in what is left.
    assert (
        service.reserve(
            organization_id="org_a", user_id="u1", prompt_chars=3
        ).cost_micros
        == 17
    )


def test_in_flight_runs_hold_budget_against_each_other(monkeypatch) -> None:
    priced(
        monkeypatch, price="1", org_daily="0.0005", max_output="100"
    )  # 500 micro-USD
    service, _store, _clock = make_service()
    first = service.reserve(
        organization_id="org_a", user_id="u1", prompt_chars=300
    )  # 200
    second = service.reserve(
        organization_id="org_a", user_id="u2", prompt_chars=300
    )  # 200
    with pytest.raises(HTTPException) as refused:
        service.reserve(
            organization_id="org_a", user_id="u3", prompt_chars=300
        )  # would be 600
    assert refused.value.detail["code"] == "ai_budget_exceeded"

    service.release(first)  # a run that ended without spending frees its hold
    service.reserve(organization_id="org_a", user_id="u3", prompt_chars=300)
    service.release(second)


def test_actual_spend_replaces_the_hold(monkeypatch) -> None:
    priced(monkeypatch, price="1", org_daily="0.0005", max_output="100")
    service, store, clock = make_service()
    reservation = service.reserve(
        organization_id="org_a", user_id="u1", prompt_chars=300
    )
    record = service.record(
        reservation, run_id="r", provider="openai", model="m",
        input_tokens=50, output_tokens=20, estimated=False, status="completed",
    )  # fmt: skip
    service.release(reservation)
    assert record.cost_micros == 70
    assert store.spent(day_window(clock()).since, organization_id="org_a") == 70
    assert not service._reservations


def test_abandoned_reservations_expire(monkeypatch) -> None:
    priced(monkeypatch, price="1", org_daily="0.0003", max_output="100")
    service, _store, clock = make_service()
    service.reserve(
        organization_id="org_a", user_id="u1", prompt_chars=300
    )  # 200 of 300
    with pytest.raises(HTTPException):
        service.reserve(organization_id="org_a", user_id="u2", prompt_chars=300)
    clock.mono += 120 + 30 + 1  # run timeout + grace
    service.reserve(organization_id="org_a", user_id="u2", prompt_chars=300)


def test_each_scope_is_enforced_independently(monkeypatch) -> None:
    priced(
        monkeypatch,
        price="1",
        user_daily="0.0004",
        org_monthly="0.002",
        global_monthly="0.003",
    )
    service, _store, _clock = make_service()
    spend(service, "org_a", "heavy", 450)

    def scope_refused(org: str, user: str) -> str | None:
        try:
            service.reserve(organization_id=org, user_id=user, prompt_chars=3)
        except HTTPException as error:
            return error.detail["details"]["scope"]
        return None

    assert scope_refused("org_a", "heavy") == "user_daily"
    assert scope_refused("org_a", "light") is None  # other users of the org are fine
    spend(service, "org_a", "light", 1_600)
    assert scope_refused("org_a", "third") == "organization_monthly"
    assert scope_refused("org_b", "someone") is None  # other organizations are fine
    spend(service, "org_b", "someone", 1_000)
    assert (
        scope_refused("org_c", "anyone") == "global_monthly"
    )  # the platform-wide ceiling


def test_budgets_start_over_with_each_window(monkeypatch) -> None:
    priced(monkeypatch, price="1", org_daily="0.0003", org_monthly="0.001")
    service, _store, clock = make_service()
    spend(service, "org_a", "u1", 280)
    with pytest.raises(HTTPException):
        service.reserve(organization_id="org_a", user_id="u1", prompt_chars=300)

    clock.now = datetime(2026, 10, 14, 0, 1, tzinfo=timezone.utc)  # next day
    service.reserve(organization_id="org_a", user_id="u1", prompt_chars=3)

    spend(service, "org_a", "u1", 280)
    clock.now = datetime(2026, 11, 1, 0, 1, tzinfo=timezone.utc)  # next month
    service.reserve(organization_id="org_a", user_id="u1", prompt_chars=300)


def test_a_zero_cap_blocks_everything_and_no_cap_blocks_nothing(monkeypatch) -> None:
    priced(monkeypatch, price="1", org_daily="0")
    service, _store, _clock = make_service()
    with pytest.raises(HTTPException):
        service.reserve(organization_id="org_a", user_id="u1", prompt_chars=3)

    monkeypatch.delenv("HELIX_AI_BUDGET_ORG_DAILY_USD")
    service.reserve(organization_id="org_a", user_id="u1", prompt_chars=3)


def test_unpriced_usage_cannot_hit_a_cap(monkeypatch) -> None:
    monkeypatch.setenv("HELIX_AI_BUDGET_ORG_DAILY_USD", "0")  # no prices: the free stub
    service, _store, _clock = make_service()
    assert (
        service.reserve(
            organization_id="org_a", user_id="u1", prompt_chars=10_000
        ).cost_micros
        == 0
    )


def test_concurrent_runs_per_user_are_limited_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("HELIX_AI_MAX_CONCURRENT_RUNS_PER_USER", "2")
    service, _store, _clock = make_service()
    first = service.reserve(organization_id="org_a", user_id="u1", prompt_chars=1)
    service.reserve(organization_id="org_a", user_id="u1", prompt_chars=1)
    with pytest.raises(HTTPException) as refused:
        service.reserve(organization_id="org_a", user_id="u1", prompt_chars=1)
    assert refused.value.detail["code"] == "ai_concurrency_limit"
    service.reserve(
        organization_id="org_a", user_id="u2", prompt_chars=1
    )  # others unaffected
    service.release(first)
    service.reserve(organization_id="org_a", user_id="u1", prompt_chars=1)


# --------------------------------------------------------------------------- #
# Runs, end to end
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(request):
    return request.getfixturevalue(request.param)


def _session(client, headers=SCIENTIST, org="org_demo") -> str:
    return client.post(
        "/api/v1/ai/sessions", headers=headers, json={"organization_id": org}
    ).json()["id"]


def _run(client, session_id, message="hi", headers=SCIENTIST):
    return client.post(
        "/api/v1/ai/runs",
        headers=headers,
        json={"session_id": session_id, "message": message},
    )


def _one_run_budget_usd() -> str:
    """A cap that admits exactly one run's reservation (the stub then overshoots it)."""
    from helixos.ai.service import AgentService

    settings = limits.ai_limit_settings()
    chars = len(AgentService()._load_system_prompt()) + len("hi") + 200
    micros = cost_micros(estimate_tokens(chars), settings.max_output_tokens, settings)
    return str(micros / 1_000_000)


@pytest.mark.parametrize("client", ELN_CLIENT_FIXTURES, indirect=True)
def test_a_run_is_recorded_and_the_next_is_refused_over_budget(
    client, monkeypatch
) -> None:
    priced(monkeypatch, price="1000")
    monkeypatch.setenv("HELIX_AI_BUDGET_ORG_DAILY_USD", _one_run_budget_usd())
    session_id = _session(client)

    first = _run(client, session_id)
    assert first.status_code == 200 and "event: done" in first.text
    done = json.loads(first.text.split("event: done\ndata: ")[1].split("\n")[0])
    assert done["usage"]["estimated"] is True and done["usage"]["output_tokens"] > 0

    # Refused up front, as a normal error, not a half-started stream.
    second = _run(client, session_id)
    body = second.json()["error"]
    assert second.status_code == 429 and body["code"] == "ai_budget_exceeded"
    assert body["details"]["scope"] == "organization_daily"
    assert int(second.headers["retry-after"]) > 0
    assert second.headers["content-type"].startswith("application/json")

    # A different organization has its own budget.
    other = _run(client, _session(client, ADMIN, "org_qc"), headers=ADMIN)
    assert other.status_code == 200

    # Spend is in the audit trail of the run that incurred it.
    events = client.get(
        "/api/v1/audit/events?organization_id=org_demo", headers=ADMIN
    ).json()
    completed = next(e for e in events if e["event_type"] == "ai.run_completed")
    assert completed["payload"]["usage_estimated"] is True
    assert float(completed["payload"]["cost_usd"]) > 0


@pytest.mark.parametrize("client", ELN_CLIENT_FIXTURES, indirect=True)
def test_admins_can_read_usage_against_the_caps(client, monkeypatch) -> None:
    priced(monkeypatch, price="1000", org_daily="50", org_monthly="500")
    assert _run(client, _session(client)).status_code == 200

    summary = client.get(
        "/api/v1/ai/usage?organization_id=org_demo", headers=ADMIN
    ).json()
    assert float(summary["organization_day"]["spent_usd"]) > 0
    assert summary["organization_day"]["cap_usd"] == "50.000000"
    assert summary["organization_month"]["cap_usd"] == "500.000000"
    assert (
        summary["organization_day"]["spent_usd"]
        == summary["organization_month"]["spent_usd"]
    )
    assert summary["max_output_tokens_per_run"] == 16

    # Scientists use the agent but do not see the money.
    assert (
        client.get(
            "/api/v1/ai/usage?organization_id=org_demo", headers=SCIENTIST
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/ai/usage?organization_id=org_qc", headers=SCIENTIST
        ).status_code
        == 403
    )


def test_overlong_messages_are_refused_before_any_work(
    memory_client, monkeypatch
) -> None:
    monkeypatch.setenv("HELIX_AI_MAX_INPUT_CHARS", "100")
    session_id = _session(memory_client)
    refused = _run(memory_client, session_id, message="x" * 101)
    assert (refused.status_code, refused.json()["error"]["code"]) == (
        422,
        "message_too_long",
    )
    assert refused.json()["error"]["details"]["limit"] == 100
    assert _run(memory_client, session_id, message="x" * 100).status_code == 200


def test_agent_run_rate_limits_apply_per_user_and_per_organization(
    memory_client, monkeypatch
) -> None:
    from helixos import ratelimit

    ratelimit.rate_limiter.reset()
    monkeypatch.setenv("HELIX_RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("HELIX_RATE_LIMIT_AI_RUN_PER_MINUTE", "2")
    monkeypatch.setenv("HELIX_RATE_LIMIT_AI_RUN_ORG_PER_MINUTE", "3")
    session_id = _session(memory_client)
    assert [_run(memory_client, session_id).status_code for _ in range(3)] == [
        200,
        200,
        429,
    ]

    # A second user of the same org is not blocked by the first, until the org itself is.
    admin_session = _session(memory_client, ADMIN)
    assert _run(memory_client, admin_session, headers=ADMIN).status_code == 200
    blocked = _run(memory_client, admin_session, headers=ADMIN)
    assert (
        blocked.status_code == 429
        and blocked.json()["error"]["details"]["scope"] == "ai_run_org"
    )
    ratelimit.rate_limiter.reset()


# --------------------------------------------------------------------------- #
# Settlement on every exit path (service level)
# --------------------------------------------------------------------------- #
class FakeProvider:
    name = "openai"
    model = "fake-model"

    def __init__(
        self, tokens=("alpha ", "beta "), usage: Usage | None = None, delay: float = 0.0
    ):
        self.tokens, self.usage, self.delay = tokens, usage, delay
        self.seen_max_output_tokens: int | None = None
        self._final_usage = usage

    async def stream_response(self, context, *, max_output_tokens):
        self.seen_max_output_tokens = max_output_tokens
        for token in self.tokens:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield token
        self.usage = self._final_usage


def _drive(service, actor, session_id, provider, *, close_after: int | None = None):
    """Run the stream to the end (or abandon it after N frames); return the frames."""
    frames: list[str] = []

    async def scenario():
        stream = service.stream_run(session_id, "hello", actor)
        async for frame in stream:
            frames.append(frame)
            if close_after is not None and len(frames) >= close_after:
                await stream.aclose()
                break

    asyncio.run(scenario())
    return frames


def _service_and_actor(monkeypatch, provider):
    monkeypatch.setattr("helixos.ai.service.get_agent_provider", lambda: provider)
    service = AgentService()
    actor = DEMO_TOKENS["org-demo-token"]
    return service, actor, service.create_session("org_demo", actor).id


def _ledger_total() -> int:
    return budget_service.store.spent(datetime(2000, 1, 1, tzinfo=timezone.utc))


def test_provider_reported_usage_is_what_gets_charged(monkeypatch) -> None:
    priced(monkeypatch, price="2", max_output="64")
    provider = FakeProvider(usage=Usage(input_tokens=1000, output_tokens=250))
    service, actor, session_id = _service_and_actor(monkeypatch, provider)

    frames = _drive(service, actor, session_id, provider)

    assert provider.seen_max_output_tokens == 64  # the ceiling reached the provider
    assert _ledger_total() == 1250 * 2
    run = next(iter(service._runs.values()))
    assert (run.input_tokens, run.output_tokens, run.usage_estimated) == (
        1000,
        250,
        False,
    )
    assert '"estimated": false' in frames[-1]
    assert not budget_service._reservations


def test_unreported_usage_is_estimated_from_what_was_streamed(monkeypatch) -> None:
    priced(monkeypatch, price="1")
    provider = FakeProvider(tokens=("x" * 30,), usage=None)
    service, actor, session_id = _service_and_actor(monkeypatch, provider)
    _drive(service, actor, session_id, provider)
    run = next(iter(service._runs.values()))
    assert run.usage_estimated is True and run.output_tokens == 10  # 30 chars / 3
    assert run.input_tokens == estimate_tokens(
        len(service._load_system_prompt()) + len("hello") + 200
    )


def test_a_client_that_disconnects_is_still_charged_and_the_hold_released(
    monkeypatch,
) -> None:
    priced(monkeypatch, price="1")
    provider = FakeProvider(tokens=("a" * 90, "b" * 90, "c" * 90))
    service, actor, session_id = _service_and_actor(monkeypatch, provider)

    # 2 tool_call frames, then the first token, then walk away.
    _drive(service, actor, session_id, provider, close_after=3)

    run = next(iter(service._runs.values()))
    assert run.status == "cancelled"
    assert run.output_tokens == 30  # only the first 90 chars had been streamed
    assert _ledger_total() > 0
    assert not budget_service._reservations


def test_a_run_that_fails_before_the_model_is_called_costs_nothing(monkeypatch) -> None:
    priced(monkeypatch, price="1000")
    provider = FakeProvider()
    service, actor, session_id = _service_and_actor(monkeypatch, provider)

    def boom(_actor):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("helixos.ai.service.experiment_service.list_experiments", boom)
    frames = _drive(service, actor, session_id, provider)

    assert any("event: error" in frame for frame in frames)
    assert _ledger_total() == 0
    assert provider.seen_max_output_tokens is None
    assert not budget_service._reservations


def test_a_run_that_exceeds_the_time_limit_is_stopped_and_charged(monkeypatch) -> None:
    priced(monkeypatch, price="1")
    real = limits.ai_limit_settings
    monkeypatch.setattr(
        "helixos.ai.service.limits.ai_limit_settings",
        lambda: dataclasses.replace(real(), run_timeout_seconds=0.05),
    )
    provider = FakeProvider(tokens=("one ", "two ", "three "), delay=0.1)
    service, actor, session_id = _service_and_actor(monkeypatch, provider)

    frames = _drive(service, actor, session_id, provider)

    error = next(frame for frame in frames if frame.startswith("event: error"))
    assert "time limit" in error
    run = next(iter(service._runs.values()))
    assert run.status == "failed" and run.provider == "openai"
    assert not budget_service._reservations


def test_a_budget_refusal_never_starts_a_run(monkeypatch) -> None:
    priced(monkeypatch, price="1000", org_daily="0")
    provider = FakeProvider()
    service, actor, session_id = _service_and_actor(monkeypatch, provider)
    with pytest.raises(HTTPException) as refused:
        _drive(service, actor, session_id, provider)
    assert refused.value.detail["code"] == "ai_budget_exceeded"
    assert not service._runs and provider.seen_max_output_tokens is None


def test_ledger_is_a_module_singleton_replaced_at_startup() -> None:
    assert isinstance(budget_module.build_usage_store(), MemoryUsageStore)
