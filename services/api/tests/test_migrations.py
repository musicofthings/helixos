"""Versioned migration runner."""

import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from helixos.db import migrations
from helixos.db.migrations import (
    MIGRATIONS,
    applied_versions,
    column_exists,
    upgrade,
)


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}", future=True)
    yield engine
    engine.dispose()


def test_fresh_database_gets_all_tables_and_is_versioned(engine) -> None:
    applied = upgrade(engine)
    assert applied == [name for name, _ in MIGRATIONS]
    tables = set(inspect(engine).get_table_names())
    assert {"audit_events", "helix_schema_migrations"} <= tables
    assert applied_versions(engine) == applied


def test_upgrade_is_idempotent(engine) -> None:
    upgrade(engine)
    assert upgrade(engine) == []


def test_unversioned_legacy_database_is_adopted_without_data_loss(engine) -> None:
    upgrade(engine)
    table = next(
        t for t in inspect(engine).get_table_names() if t.startswith("eln_") or t == "audit_events"
    )
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE helix_schema_migrations"))
        # Simulate a database created before a nullable column was declared.
        inspector = inspect(connection)
        nullable = [
            c["name"]
            for c in inspector.get_columns(table)
            if c["nullable"] and not c.get("primary_key")
        ]
    assert nullable, "expected a nullable column to drop for the simulation"
    with engine.begin() as connection:
        connection.execute(text(f'ALTER TABLE "{table}" DROP COLUMN "{nullable[0]}"'))
    assert not column_exists(engine.connect(), table, nullable[0])

    assert upgrade(engine) == [name for name, _ in MIGRATIONS]
    assert column_exists(engine.connect(), table, nullable[0])


def test_new_migration_runs_once_and_in_order(engine, monkeypatch) -> None:
    upgrade(engine)
    calls: list[str] = []

    def add_marker(connection, op) -> None:
        calls.append("0002")
        if not column_exists(connection, "helix_schema_migrations", "note"):
            with op.batch_alter_table("helix_schema_migrations") as batch:
                batch.add_column(__import__("sqlalchemy").Column("note", __import__("sqlalchemy").String(20)))

    plan = [*MIGRATIONS, ("0002_add_note", add_marker)]
    assert upgrade(engine, plan) == ["0002_add_note"]
    assert upgrade(engine, plan) == []
    assert calls == ["0002"]
    assert column_exists(engine.connect(), "helix_schema_migrations", "note")


def test_failed_migration_is_not_recorded(engine) -> None:
    upgrade(engine)

    def boom(connection, op) -> None:
        connection.execute(text("CREATE TABLE half_done (id INTEGER)"))
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        upgrade(engine, [*MIGRATIONS, ("0002_boom", boom)])
    # Only the version record is guaranteed: pysqlite commits DDL implicitly, so
    # half_done may remain on SQLite (PostgreSQL rolls it back).
    assert "0002_boom" not in applied_versions(engine)


def test_unordered_plan_is_rejected(engine) -> None:
    with pytest.raises(RuntimeError):
        upgrade(engine, [("0002_b", lambda c, o: None), ("0001_a", lambda c, o: None)])
