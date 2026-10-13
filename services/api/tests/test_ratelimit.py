"""Rate limiting and request-size limits."""

import pytest
from fastapi.testclient import TestClient

from helixos import ratelimit
from helixos.main import create_app
from helixos.ratelimit import RateLimiter

DEMO = {"Authorization": "Bearer org-demo-token"}
ADMIN = {"Authorization": "Bearer demo-admin-token"}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# --------------------------------------------------------------------------- #
# The limiter
# --------------------------------------------------------------------------- #
def test_allows_up_to_the_limit_then_blocks_with_a_retry_time() -> None:
    clock = Clock()
    limiter = RateLimiter(clock=clock)
    results = [limiter.hit("s", "k", limit=3, per_seconds=60) for _ in range(4)]

    assert [r.allowed for r in results] == [True, True, True, False]
    assert [r.remaining for r in results[:3]] == [2, 1, 0]
    assert results[3].retry_after == 20  # one token refills every 60/3 seconds


def test_tokens_refill_over_time() -> None:
    clock = Clock()
    limiter = RateLimiter(clock=clock)
    for _ in range(3):
        limiter.hit("s", "k", limit=3, per_seconds=60)
    assert not limiter.hit("s", "k", limit=3, per_seconds=60).allowed

    clock.now += 20
    assert limiter.hit("s", "k", limit=3, per_seconds=60).allowed
    assert not limiter.hit("s", "k", limit=3, per_seconds=60).allowed

    clock.now += 600  # long idle never banks more than the burst
    assert [limiter.hit("s", "k", 3, 60).allowed for _ in range(4)] == [
        True,
        True,
        True,
        False,
    ]


def test_keys_and_scopes_are_independent() -> None:
    limiter = RateLimiter(clock=Clock())
    assert limiter.hit("a", "alice", 1).allowed
    assert not limiter.hit("a", "alice", 1).allowed
    assert limiter.hit("a", "bob", 1).allowed
    assert limiter.hit("b", "alice", 1).allowed


def test_memory_is_bounded_and_idle_entries_go_first() -> None:
    clock = Clock()
    limiter = RateLimiter(clock=clock, max_keys=100)
    for i in range(100):
        limiter.hit("s", f"idle{i}", 5, 60)
    clock.now += 120  # all of those have fully refilled
    for i in range(60):
        limiter.hit("s", f"active{i}", 5, 60)
    assert len(limiter._buckets) <= 100
    # An actively limited key survives the trimming of idle ones.
    for _ in range(5):
        limiter.hit("s", "attacker", 5, 60)
    for i in range(80):
        limiter.hit("s", f"more{i}", 5, 60)
    assert not limiter.hit("s", "attacker", 5, 60).allowed


# --------------------------------------------------------------------------- #
# Through the API
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def fresh_limiter(monkeypatch):
    ratelimit.rate_limiter.reset()
    for name in (
        "HELIX_RATE_LIMIT_ENABLED",
        "HELIX_RATE_LIMIT_ACTOR_PER_MINUTE",
        "HELIX_RATE_LIMIT_WRITE_PER_MINUTE",
        "HELIX_RATE_LIMIT_AUTH_FAILURES_PER_MINUTE",
        "HELIX_RATE_LIMIT_INVITE_ACCEPT_PER_HOUR",
        "HELIX_RATE_LIMIT_AI_SESSION_PER_MINUTE",
        "HELIX_RATE_LIMIT_MCP_JOB_PER_MINUTE",
        "HELIX_TRUSTED_PROXY_HOPS",
        "HELIX_MAX_BODY_BYTES",
    ):
        monkeypatch.delenv(name, raising=False)
    yield
    ratelimit.rate_limiter.reset()


@pytest.fixture
def limited(monkeypatch) -> TestClient:
    monkeypatch.setenv("HELIX_RATE_LIMIT_ENABLED", "1")
    return TestClient(create_app())


def test_limits_are_off_by_default_in_development(memory_client) -> None:
    statuses = {
        memory_client.get("/api/v1/organizations", headers=DEMO).status_code
        for _ in range(50)
    }
    assert statuses == {200}


def test_a_user_who_exceeds_the_request_limit_gets_a_429_envelope(
    limited, monkeypatch
) -> None:
    monkeypatch.setenv("HELIX_RATE_LIMIT_ACTOR_PER_MINUTE", "5")
    codes = [
        limited.get("/api/v1/organizations", headers=DEMO).status_code for _ in range(6)
    ]
    assert codes == [200] * 5 + [429]

    blocked = limited.get("/api/v1/organizations", headers=DEMO)
    body = blocked.json()["error"]
    assert (blocked.status_code, body["code"]) == (429, "rate_limited")
    assert body["details"]["scope"] == "actor" and body["details"]["limit"] == 5
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.headers["x-ratelimit-limit"] == "5"
    assert "request_id" in body

    # Someone else is unaffected by that user's burst.
    assert limited.get("/api/v1/organizations", headers=ADMIN).status_code == 200


def test_writes_have_a_stricter_limit_than_reads(limited, monkeypatch) -> None:
    monkeypatch.setenv("HELIX_RATE_LIMIT_WRITE_PER_MINUTE", "3")
    workspace = {"organization_id": "org_demo", "name": "W", "category": "custom"}
    codes = [
        limited.post("/api/v1/workspaces", headers=DEMO, json=workspace).status_code
        for _ in range(4)
    ]
    assert codes == [201, 201, 201, 429]
    assert (
        limited.get("/api/v1/organizations", headers=DEMO).status_code == 200
    )  # reads still fine


def test_repeated_bad_tokens_are_throttled_but_valid_ones_are_not(
    limited, monkeypatch
) -> None:
    monkeypatch.setenv("HELIX_RATE_LIMIT_AUTH_FAILURES_PER_MINUTE", "3")
    bad = {"Authorization": "Bearer nope"}
    codes = [
        limited.get("/api/v1/organizations", headers=bad).status_code for _ in range(5)
    ]
    assert codes == [401, 401, 401, 429, 429]
    assert (
        limited.get("/api/v1/organizations").status_code == 429
    )  # no token counts too

    # Many legitimate users can share a proxy address: valid tokens still pass.
    assert limited.get("/api/v1/organizations", headers=DEMO).status_code == 200


def test_forwarded_for_is_trusted_only_from_the_right(limited, monkeypatch) -> None:
    monkeypatch.setenv("HELIX_RATE_LIMIT_AUTH_FAILURES_PER_MINUTE", "2")
    monkeypatch.setenv("HELIX_TRUSTED_PROXY_HOPS", "1")
    bad = {"Authorization": "Bearer nope"}

    def attempt(forwarded: str) -> int:
        return limited.get(
            "/api/v1/organizations", headers={**bad, "X-Forwarded-For": forwarded}
        ).status_code

    # A client rotating the left-hand entries cannot dodge the bucket of the real address.
    assert [attempt(f"spoof-{i}, 9.9.9.9") for i in range(4)] == [401, 401, 429, 429]
    # A different real address has its own bucket.
    assert attempt("spoof, 8.8.8.8") == 401


def test_forwarded_for_is_ignored_without_trusted_proxies(limited, monkeypatch) -> None:
    monkeypatch.setenv("HELIX_RATE_LIMIT_AUTH_FAILURES_PER_MINUTE", "2")
    bad = {"Authorization": "Bearer nope"}
    codes = [
        limited.get(
            "/api/v1/organizations", headers={**bad, "X-Forwarded-For": f"1.1.1.{i}"}
        ).status_code
        for i in range(4)
    ]
    assert codes == [401, 401, 429, 429]


def test_invite_token_guessing_is_slowed(limited, monkeypatch) -> None:
    monkeypatch.setenv("HELIX_RATE_LIMIT_INVITE_ACCEPT_PER_HOUR", "2")
    codes = [
        limited.post(
            f"/api/v1/workspace-invites/guess{i}/accept", headers=DEMO
        ).status_code
        for i in range(4)
    ]
    assert codes == [404, 404, 429, 429]


def test_agent_session_creation_is_limited(limited, monkeypatch) -> None:
    monkeypatch.setenv("HELIX_RATE_LIMIT_AI_SESSION_PER_MINUTE", "2")
    codes = [
        limited.post(
            "/api/v1/ai/sessions", headers=DEMO, json={"organization_id": "org_demo"}
        ).status_code
        for _ in range(3)
    ]
    assert codes == [201, 201, 429]


def test_connector_jobs_are_limited(limited, monkeypatch) -> None:
    monkeypatch.setenv("HELIX_RATE_LIMIT_MCP_JOB_PER_MINUTE", "2")
    job = {
        "organization_id": "org_demo",
        "connector_id": "does-not-exist",
        "tool": "x",
        "arguments": {},
    }
    codes = [
        limited.post("/api/v1/mcp/jobs", headers=DEMO, json=job).status_code
        for _ in range(3)
    ]
    assert codes == [404, 404, 429]


def test_retry_after_is_readable_by_browsers(limited, monkeypatch) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000")
    response = limited.get(
        "/api/v1/organizations", headers={**DEMO, "Origin": "http://localhost:3000"}
    )
    assert "retry-after" in response.headers["access-control-expose-headers"].lower()


# --------------------------------------------------------------------------- #
# Request size
# --------------------------------------------------------------------------- #
@pytest.fixture
def small_bodies(monkeypatch) -> TestClient:
    monkeypatch.setenv("HELIX_MAX_BODY_BYTES", "1024")
    return TestClient(create_app())


def test_oversized_declared_body_is_refused_before_it_is_read(small_bodies) -> None:
    response = small_bodies.post(
        "/api/v1/workspaces",
        headers={**DEMO, "Origin": "http://localhost:3000"},
        json={"organization_id": "org_demo", "name": "x" * 5000, "category": "custom"},
    )
    body = response.json()["error"]
    assert (response.status_code, body["code"]) == (413, "payload_too_large")
    assert body["details"]["limit_bytes"] == 1024 and "request_id" in body
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_streamed_body_without_a_content_length_is_still_capped(small_bodies) -> None:
    def chunks():
        for _ in range(10):
            yield b'{"organization_id": "org_demo", "name": "' + b"y" * 400 + b'"}'

    response = small_bodies.post("/api/v1/workspaces", headers=DEMO, content=chunks())
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_bodies_under_the_limit_are_untouched(small_bodies) -> None:
    response = small_bodies.post(
        "/api/v1/workspaces",
        headers=DEMO,
        json={"organization_id": "org_demo", "name": "small", "category": "custom"},
    )
    assert response.status_code == 201
