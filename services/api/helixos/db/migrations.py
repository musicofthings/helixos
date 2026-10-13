"""Versioned schema migrations.

Each migration is an ordered ``(version, function)`` pair. Applied versions are
recorded in ``helix_schema_migrations`` and run exactly once, in order, each in
its own transaction. PostgreSQL rolls a failed migration back entirely; SQLite
with pysqlite commits DDL implicitly, so a failed migration there is not recorded
but may leave partial DDL behind — write SQLite-safe migrations to be re-runnable
(``column_exists`` / ``index_exists`` guards). Migrations receive an Alembic ``Operations``
object, so ``op.add_column`` / ``op.batch_alter_table`` work on SQLite and
PostgreSQL alike (use ``batch_alter_table`` for anything SQLite cannot ALTER,
such as constraints or NOT NULL changes).

Migrations are plain Python rather than an Alembic script directory so the
PyInstaller desktop sidecar needs no extra data files.

Rules for adding one:
* Append to ``MIGRATIONS``; never edit or reorder an applied entry.
* ``0001_baseline`` builds tables from the *current* ORM metadata on fresh
  databases, so later migrations must be idempotent (see ``column_exists`` /
  ``index_exists``): a fresh database already has what they add.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from datetime import datetime, timezone

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    inspect,
    select,
    text,
)
from sqlalchemy.engine import Connection, Engine

from helixos.db.base import Base

logger = logging.getLogger("helixos.db.migrations")

MigrationFn = Callable[[Connection, Operations], None]

_ADVISORY_LOCK_KEY = 727_274  # serializes concurrent starters on PostgreSQL

_version_metadata = MetaData()
_versions = Table(
    "helix_schema_migrations",
    _version_metadata,
    Column("version", String(64), primary_key=True),
    Column("applied_at", DateTime(timezone=True), nullable=False),
)


def column_exists(connection: Connection, table: str, column: str) -> bool:
    inspector = inspect(connection)
    if table not in inspector.get_table_names():
        return False
    return column in {col["name"] for col in inspector.get_columns(table)}


def index_exists(connection: Connection, table: str, index: str) -> bool:
    inspector = inspect(connection)
    if table not in inspector.get_table_names():
        return False
    return index in {idx["name"] for idx in inspector.get_indexes(table)}


def _baseline(connection: Connection, op: Operations) -> None:
    """Create missing tables, then add nullable columns declared since a database
    was first created (the behaviour databases relied on before versioning)."""
    # Importing registers every ORM model on Base.metadata.
    from helixos.audit.orm import AuditEventORM  # noqa: F401
    from helixos.auth import orm as auth_orm  # noqa: F401
    from helixos.eln import orm as eln_orm  # noqa: F401

    Base.metadata.create_all(connection)

    inspector = inspect(connection)
    for table in Base.metadata.tables.values():
        if not isinstance(table, Table):
            continue
        present = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present or not column.nullable:
                continue
            column_type = column.type.compile(dialect=connection.dialect)
            connection.execute(
                text(
                    f'ALTER TABLE "{table.name}" '
                    f'ADD COLUMN "{column.name}" {column_type}'
                )
            )


# (index name, table, columns) — frozen here; later indexes belong in a later migration.
_LIST_INDEXES: list[tuple[str, str, list[str]]] = [
    (
        "ix_eln_list_workspaces",
        "eln_workspaces",
        ["organization_id", "created_at", "id"],
    ),
    (
        "ix_eln_list_projects_org",
        "eln_projects",
        ["organization_id", "created_at", "id"],
    ),
    ("ix_eln_list_projects_ws", "eln_projects", ["workspace_id", "created_at", "id"]),
    (
        "ix_eln_list_protocols_org",
        "eln_protocols",
        ["organization_id", "created_at", "id"],
    ),
    ("ix_eln_list_protocols_ws", "eln_protocols", ["workspace_id", "created_at", "id"]),
    (
        "ix_eln_list_experiments_org",
        "eln_experiments",
        ["organization_id", "created_at", "id"],
    ),
    (
        "ix_eln_list_experiments_project",
        "eln_experiments",
        ["project_id", "created_at", "id"],
    ),
    ("ix_eln_list_samples", "eln_samples", ["experiment_id", "created_at", "id"]),
    ("ix_eln_list_datasets", "eln_datasets", ["sample_id", "created_at", "id"]),
]


def _list_indexes(connection: Connection, op: Operations) -> None:
    """Composite indexes matching the ORDER BY of the paged ELN list queries.

    Fresh databases already have them (the baseline builds from the models), so
    this only fills in databases created before pagination moved into SQL.
    """
    for name, table, columns in _LIST_INDEXES:
        if not index_exists(connection, table, name):
            op.create_index(name, table, columns)


def _auth_tables(connection: Connection, op: Operations) -> None:
    """Organizations, users, memberships and member invites.

    Fresh databases already have them (the baseline builds from the models);
    ``checkfirst`` makes this a no-op there.
    """
    from helixos.auth import orm as auth_orm

    tables = [
        auth_orm.OrganizationORM.__table__,
        auth_orm.UserORM.__table__,
        auth_orm.MembershipORM.__table__,
        auth_orm.MemberInviteORM.__table__,
    ]
    Base.metadata.create_all(connection, tables=tables, checkfirst=True)


MIGRATIONS: list[tuple[str, MigrationFn]] = [
    ("0001_baseline", _baseline),
    ("0002_eln_list_indexes", _list_indexes),
    ("0003_auth_tables", _auth_tables),
]


def applied_versions(engine: Engine) -> list[str]:
    """Return applied migration versions in order (empty if never migrated)."""
    with engine.connect() as connection:
        if "helix_schema_migrations" not in inspect(connection).get_table_names():
            return []
        rows = connection.execute(
            select(_versions.c.version).order_by(_versions.c.version)
        )
        return [row[0] for row in rows]


def upgrade(
    engine: Engine, migrations: list[tuple[str, MigrationFn]] | None = None
) -> list[str]:
    """Apply every pending migration; return the versions applied by this call."""
    plan = MIGRATIONS if migrations is None else migrations
    names = [name for name, _ in plan]
    if len(set(names)) != len(names) or names != sorted(names):
        raise RuntimeError("Migrations must have unique, lexically ordered versions")

    applied_now: list[str] = []
    for version, fn in plan:
        with engine.begin() as connection:
            if connection.dialect.name == "postgresql":
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"),
                    {"key": _ADVISORY_LOCK_KEY},
                )
            # Under the lock so concurrent starters cannot race the CREATE TABLE.
            _version_metadata.create_all(connection)
            already = connection.execute(
                select(_versions.c.version).where(_versions.c.version == version)
            ).first()
            if already is not None:
                continue
            fn(connection, Operations(MigrationContext.configure(connection)))
            connection.execute(
                _versions.insert().values(
                    version=version, applied_at=datetime.now(timezone.utc)
                )
            )
            applied_now.append(version)
            logger.info("migration applied", extra={"version": version})
    return applied_now


def main(argv: list[str] | None = None) -> int:
    """``python -m helixos.db.migrations [status|upgrade]``"""
    from helixos.db.session import get_engine

    command = (argv if argv is not None else sys.argv[1:] or ["status"])[0]
    engine = get_engine()
    if engine is None:
        print("HELIX_DATABASE_URL is not configured", file=sys.stderr)
        return 1
    if command == "upgrade":
        applied = upgrade(engine)
        print("Applied: " + (", ".join(applied) if applied else "nothing (up to date)"))
        return 0
    if command == "status":
        done = set(applied_versions(engine))
        for version, _ in MIGRATIONS:
            print(f"{'applied' if version in done else 'pending':8} {version}")
        return 0
    print(f"Unknown command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
