"""Versioned migration runner."""

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
        t
        for t in inspect(engine).get_table_names()
        if t.startswith("eln_") or t == "audit_events"
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
        calls.append("9000")
        if not column_exists(connection, "helix_schema_migrations", "note"):
            with op.batch_alter_table("helix_schema_migrations") as batch:
                batch.add_column(
                    __import__("sqlalchemy").Column(
                        "note", __import__("sqlalchemy").String(20)
                    )
                )

    plan = [*MIGRATIONS, ("9000_test_add_note", add_marker)]
    assert upgrade(engine, plan) == ["9000_test_add_note"]
    assert upgrade(engine, plan) == []
    assert calls == ["9000"]
    assert column_exists(engine.connect(), "helix_schema_migrations", "note")


def test_failed_migration_is_not_recorded(engine) -> None:
    upgrade(engine)

    def boom(connection, op) -> None:
        connection.execute(text("CREATE TABLE half_done (id INTEGER)"))
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        upgrade(engine, [*MIGRATIONS, ("9000_test_boom", boom)])
    # Only the version record is guaranteed: pysqlite commits DDL implicitly, so
    # half_done may remain on SQLite (PostgreSQL rolls it back).
    assert "9000_test_boom" not in applied_versions(engine)


def test_unordered_plan_is_rejected(engine) -> None:
    with pytest.raises(RuntimeError):
        upgrade(engine, [("0002_b", lambda c, o: None), ("0001_a", lambda c, o: None)])


def test_list_index_migration_upgrades_a_database_that_lacks_the_indexes(
    engine,
) -> None:
    upgrade(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX ix_eln_list_projects_org"))
        connection.execute(text("DROP INDEX ix_eln_list_samples"))
        connection.execute(
            text(
                "DELETE FROM helix_schema_migrations WHERE version = '0002_eln_list_indexes'"
            )
        )

    assert upgrade(engine) == ["0002_eln_list_indexes"]
    names = {i["name"] for i in inspect(engine).get_indexes("eln_projects")}
    assert "ix_eln_list_projects_org" in names
    assert "ix_eln_list_samples" in {
        i["name"] for i in inspect(engine).get_indexes("eln_samples")
    }


def test_fresh_database_has_every_frozen_list_index(engine) -> None:
    upgrade(engine)
    for name, table, _columns in migrations._LIST_INDEXES:
        assert name in {i["name"] for i in inspect(engine).get_indexes(table)}, name


def test_auth_tables_are_added_to_a_database_migrated_before_they_existed(
    tmp_path,
) -> None:
    from sqlalchemy import inspect, text

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}", future=True)
    upgrade(engine)
    with engine.begin() as connection:
        for table in (
            "auth_member_invites",
            "auth_memberships",
            "auth_users",
            "auth_organizations",
        ):
            connection.execute(text(f"DROP TABLE {table}"))
        connection.execute(
            text(
                "DELETE FROM helix_schema_migrations WHERE version = '0003_auth_tables'"
            )
        )

    assert upgrade(engine) == ["0003_auth_tables"]
    names = set(inspect(engine).get_table_names())
    assert {
        "auth_organizations",
        "auth_users",
        "auth_memberships",
        "auth_member_invites",
    } <= names


def test_ai_usage_ledger_is_added_to_a_database_migrated_before_it_existed(
    tmp_path,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}", future=True)
    upgrade(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE ai_usage"))
        connection.execute(
            text("DELETE FROM helix_schema_migrations WHERE version = '0004_ai_usage'")
        )

    assert upgrade(engine) == ["0004_ai_usage"]
    columns = {c["name"] for c in inspect(engine).get_columns("ai_usage")}
    assert {
        "organization_id",
        "user_id",
        "cost_micros",
        "estimated",
        "created_at",
    } <= columns
    indexed = {i["name"] for i in inspect(engine).get_indexes("ai_usage")}
    assert {"ix_ai_usage_org_created", "ix_ai_usage_user_created"} <= indexed
