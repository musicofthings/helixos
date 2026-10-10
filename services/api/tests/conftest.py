"""Shared pytest fixtures for the HelixOS API test suite."""

from collections.abc import Iterator

import pytest
from backends import POSTGRES_URL
from fastapi.testclient import TestClient

from helixos.db.session import reset_engine
from helixos.main import create_app


@pytest.fixture
def memory_client() -> Iterator[TestClient]:
    """A test client backed by the in-memory stores (no database)."""
    yield TestClient(create_app())


@pytest.fixture
def sqlite_client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    """A test client backed by an isolated on-disk SQLite database.

    Exercises the SQLAlchemy store implementations end-to-end.
    """
    db_path = tmp_path / "helix-test.db"
    monkeypatch.setenv("HELIX_DATABASE_URL", f"sqlite:///{db_path}")
    reset_engine()
    try:
        yield TestClient(create_app())
    finally:
        reset_engine()




def _reset_postgres_schema() -> None:
    """Drop everything so each test starts from an empty database and the
    migration runner builds the schema (exercising it on PostgreSQL too)."""
    from sqlalchemy import create_engine, text

    engine = create_engine(POSTGRES_URL, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    finally:
        engine.dispose()


@pytest.fixture
def postgres_url(monkeypatch) -> Iterator[str]:
    """An empty PostgreSQL database wired into HELIX_DATABASE_URL."""
    if not POSTGRES_URL:
        pytest.skip("HELIX_TEST_POSTGRES_URL is not set")
    _reset_postgres_schema()
    monkeypatch.setenv("HELIX_DATABASE_URL", POSTGRES_URL)
    reset_engine()
    try:
        yield POSTGRES_URL
    finally:
        reset_engine()


@pytest.fixture
def postgres_client(postgres_url) -> Iterator[TestClient]:
    """A test client backed by a clean PostgreSQL database."""
    yield TestClient(create_app())
