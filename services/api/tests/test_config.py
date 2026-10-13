"""Environment-driven hardening: startup validation, CORS, demo tokens, docs."""

import pytest
from fastapi.testclient import TestClient

from helixos import config
from helixos.ai.settings import AISettings
from helixos.config import ConfigError, validate_runtime_config
from helixos.db.session import reset_engine
from helixos.db.settings import DatabaseSettings
from helixos.main import create_app

POSTGRES = DatabaseSettings(url="postgresql+psycopg://u:p@db:5432/helix")
WEB = "https://app.example.com"
DEMO = {"Authorization": "Bearer org-demo-token"}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in (
        "HELIX_ENV",
        "ALLOWED_ORIGINS",
        "HELIX_ENABLE_DEMO_TOKENS",
        "HELIX_ENABLE_DOCS",
        "HELIX_ALLOW_UNVERIFIED_JWT",
        "HELIX_AI_PROVIDER",
        "HELIX_OPENAI_API_KEY",
        "HELIX_OIDC_ISSUER",
        "HELIX_OIDC_AUDIENCE",
        "HELIX_OIDC_JWKS_URL",
        "HELIX_OIDC_ALGORITHMS",
        "HELIX_OIDC_LEEWAY_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)


def _production_env(monkeypatch) -> None:
    monkeypatch.setenv("HELIX_ENV", "production")
    monkeypatch.setenv("ALLOWED_ORIGINS", WEB)
    monkeypatch.setenv("HELIX_AI_PROVIDER", "openai")
    monkeypatch.setenv("HELIX_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("HELIX_OIDC_ISSUER", "https://idp.example.com/")
    monkeypatch.setenv("HELIX_OIDC_AUDIENCE", "helixos-api")


def _validate(database: DatabaseSettings = POSTGRES) -> None:
    validate_runtime_config(database, AISettings.from_env())


def _problems(database: DatabaseSettings = POSTGRES) -> str:
    with pytest.raises(ConfigError) as error:
        _validate(database)
    return str(error.value)


def test_valid_production_config_passes(monkeypatch) -> None:
    _production_env(monkeypatch)
    _validate()


def test_unknown_environment_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("HELIX_ENV", "prod")
    assert "HELIX_ENV must be one of" in _problems()


def test_development_needs_no_configuration() -> None:
    _validate(DatabaseSettings(url=None))
    assert config.demo_tokens_enabled()
    assert not config.is_hosted()
    assert config.docs_enabled()


@pytest.mark.parametrize(
    ("origins", "expected"),
    [
        ("", "ALLOWED_ORIGINS is required"),
        ("*", "must not contain '*'"),
        ("app.example.com", "is not an origin"),
        ("https://app.example.com/path", "is not an origin"),
        ("http://app.example.com", "must use https in production"),
    ],
)
def test_production_rejects_bad_origins(monkeypatch, origins, expected) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv("ALLOWED_ORIGINS", origins)
    assert expected in _problems()


def test_wildcard_origin_is_rejected_in_development_too(monkeypatch) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    assert "must not contain '*'" in _problems(DatabaseSettings(url=None))


def test_origins_are_normalised_and_deduplicated(monkeypatch) -> None:
    monkeypatch.setenv(
        "ALLOWED_ORIGINS", f"{WEB}/, HTTPS://APP.example.com ,http://localhost:3000"
    )
    assert config.allowed_origins() == (WEB, "http://localhost:3000")


def test_production_rejects_demo_tokens(monkeypatch) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv("HELIX_ENABLE_DEMO_TOKENS", "1")
    assert "not allowed in production" in _problems()
    monkeypatch.delenv("HELIX_ENABLE_DEMO_TOKENS")
    assert not config.demo_tokens_enabled()


@pytest.mark.parametrize("env", ["staging", "production"])
def test_hosted_rejects_unverified_jwt(monkeypatch, env) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv("HELIX_ENV", env)
    monkeypatch.setenv("HELIX_ALLOW_UNVERIFIED_JWT", "1")
    assert "HELIX_ALLOW_UNVERIFIED_JWT" in _problems()
    assert not config.unverified_jwt_enabled()


def test_hosted_rejects_memory_store_and_production_rejects_sqlite(monkeypatch) -> None:
    _production_env(monkeypatch)
    assert "HELIX_DATABASE_URL is required" in _problems(DatabaseSettings(url=None))
    assert "requires PostgreSQL" in _problems(DatabaseSettings(url="sqlite:///x.db"))
    monkeypatch.setenv("HELIX_ENV", "staging")
    _validate(DatabaseSettings(url="sqlite:///x.db"))


def test_production_rejects_stub_and_unconfigured_ai(monkeypatch) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv("HELIX_AI_PROVIDER", "stub")
    assert "must be openai or vertex" in _problems()
    monkeypatch.setenv("HELIX_AI_PROVIDER", "openai")
    monkeypatch.delenv("HELIX_OPENAI_API_KEY")
    assert "silently fall back to the stub" in _problems()


def test_all_problems_are_reported_together(monkeypatch) -> None:
    monkeypatch.setenv("HELIX_ENV", "production")
    message = _problems(DatabaseSettings(url=None))
    assert "ALLOWED_ORIGINS is required" in message
    assert "HELIX_DATABASE_URL is required" in message
    assert "HELIX_AI_PROVIDER" in message


def test_malformed_flag_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("HELIX_ENABLE_DOCS", "true")
    assert "HELIX_ENABLE_DOCS must be 0 or 1" in _problems(DatabaseSettings(url=None))


def test_docs_default_off_only_in_production(monkeypatch) -> None:
    monkeypatch.setenv("HELIX_ENV", "staging")
    assert config.docs_enabled()
    monkeypatch.setenv("HELIX_ENV", "production")
    assert not config.docs_enabled()
    monkeypatch.setenv("HELIX_ENABLE_DOCS", "1")
    assert config.docs_enabled()


@pytest.fixture
def staging_client(tmp_path, monkeypatch):
    monkeypatch.setenv("HELIX_ENV", "staging")
    monkeypatch.setenv("ALLOWED_ORIGINS", WEB)
    monkeypatch.setenv("HELIX_DATABASE_URL", f"sqlite:///{tmp_path / 'staging.db'}")
    reset_engine()
    try:
        yield TestClient(create_app())
    finally:
        reset_engine()


def test_staging_requires_demo_tokens_opt_in(staging_client, monkeypatch) -> None:
    assert staging_client.get("/api/v1/organizations", headers=DEMO).status_code == 401
    monkeypatch.setenv("HELIX_ENABLE_DEMO_TOKENS", "1")
    assert staging_client.get("/api/v1/organizations", headers=DEMO).status_code == 200


def _preflight(
    client: TestClient, origin: str, headers: str = "authorization,content-type"
):
    return client.options(
        "/api/v1/organizations",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": headers,
        },
    )


def test_hosted_cors_allows_only_listed_origins(staging_client) -> None:
    allowed = _preflight(staging_client, WEB)
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == WEB
    assert allowed.headers["access-control-allow-credentials"] == "true"

    for origin in ("http://localhost:3000", "https://evil.example.com"):
        denied = _preflight(staging_client, origin)
        assert "access-control-allow-origin" not in denied.headers

    assert _preflight(staging_client, WEB, headers="x-custom").status_code == 400


def test_development_cors_still_allows_loopback_ports(memory_client) -> None:
    for origin in ("http://localhost:3000", "http://127.0.0.1:51234"):
        response = _preflight(memory_client, origin)
        assert response.headers["access-control-allow-origin"] == origin
    assert (
        "access-control-allow-origin"
        not in _preflight(memory_client, "https://evil.example.com").headers
    )


def test_production_hides_openapi_docs_but_keeps_health(tmp_path, monkeypatch) -> None:
    _production_env(monkeypatch)
    # Postgres is validated separately above; boot against SQLite to avoid a live server.
    monkeypatch.setattr("helixos.main.validate_runtime_config", lambda *_: None)
    monkeypatch.setenv("HELIX_DATABASE_URL", f"sqlite:///{tmp_path / 'prod.db'}")
    reset_engine()
    try:
        client = TestClient(create_app())
        assert client.get("/health").json() == {"status": "ok"}
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404
        assert client.get("/api/v1/organizations", headers=DEMO).status_code == 401
    finally:
        reset_engine()


def test_create_app_refuses_unsafe_production(monkeypatch) -> None:
    monkeypatch.setenv("HELIX_ENV", "production")
    with pytest.raises(ConfigError):
        create_app()


def test_production_requires_an_identity_provider(monkeypatch) -> None:
    _production_env(monkeypatch)
    monkeypatch.delenv("HELIX_OIDC_ISSUER")
    assert "HELIX_OIDC_ISSUER and HELIX_OIDC_AUDIENCE are required" in _problems()


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("HELIX_OIDC_AUDIENCE", "", "HELIX_OIDC_AUDIENCE is required"),
        ("HELIX_OIDC_ISSUER", "http://idp.example.com/", "must be an https URL"),
        ("HELIX_OIDC_JWKS_URL", "file:///etc/passwd", "must be an https URL"),
        ("HELIX_OIDC_ALGORITHMS", "RS256,HS256", "asymmetric algorithms only"),
        ("HELIX_OIDC_ALGORITHMS", "none", "asymmetric algorithms only"),
        ("HELIX_OIDC_LEEWAY_SECONDS", "9999", "from 0 to 300"),
    ],
)
def test_oidc_settings_are_validated(monkeypatch, name, value, expected) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv(name, value)
    assert expected in _problems()


def test_oidc_needs_a_database_even_in_development(monkeypatch) -> None:
    monkeypatch.setenv("HELIX_OIDC_ISSUER", "https://idp.example.com/")
    monkeypatch.setenv("HELIX_OIDC_AUDIENCE", "helixos-api")
    assert "needs HELIX_DATABASE_URL" in _problems(DatabaseSettings(url=None))
    _validate(DatabaseSettings(url="sqlite:///x.db"))


def test_local_http_issuer_is_allowed_for_development(monkeypatch) -> None:
    monkeypatch.setenv("HELIX_OIDC_ISSUER", "http://localhost:9000")
    monkeypatch.setenv("HELIX_OIDC_AUDIENCE", "helixos-api")
    _validate(DatabaseSettings(url="sqlite:///x.db"))
    settings = config.oidc_settings()
    assert settings is not None and settings.algorithms == ("RS256", "ES256")


# --------------------------------------------------------------------------- #
# Liveness vs readiness
# --------------------------------------------------------------------------- #
def test_ready_when_memory_backed_or_migrated(memory_client, sqlite_client) -> None:
    assert memory_client.get("/ready").json() == {"status": "ready"}
    assert sqlite_client.get("/ready").json() == {"status": "ready"}


def test_not_ready_with_a_pending_migration(sqlite_client, monkeypatch) -> None:
    from helixos.db import migrations

    monkeypatch.setattr(
        "helixos.main.MIGRATIONS",
        [*migrations.MIGRATIONS, ("9999_not_applied", lambda c, o: None)],
    )
    response = sqlite_client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}  # no internals leak to callers
    assert sqlite_client.get("/health").status_code == 200  # still alive


def test_not_ready_when_the_database_is_unreachable(sqlite_client, monkeypatch) -> None:
    def broken(*_args, **_kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr("helixos.main.get_engine", broken)
    assert sqlite_client.get("/ready").status_code == 503
    assert sqlite_client.get("/health").status_code == 200
