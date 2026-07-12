"""Shared pytest fixtures for the HelixOS API test suite."""

from collections.abc import Iterator

import pytest
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
