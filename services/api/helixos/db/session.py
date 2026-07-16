"""Database engine and session helpers."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import Table

from helixos.db.base import Base
from helixos.db.settings import DatabaseSettings, get_database_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine(settings: DatabaseSettings | None = None) -> Engine | None:
    """Return a configured SQLAlchemy engine when a database URL is set."""
    global _engine, _session_factory
    resolved = settings or get_database_settings()
    if not resolved.is_configured or resolved.url is None:
        return None

    if _engine is None:
        connect_args: dict[str, object] = {}
        if resolved.url.startswith("sqlite"):
            # Allow cross-thread use and wait on the write lock instead of
            # failing immediately when concurrent requests append audit rows.
            connect_args = {"check_same_thread": False, "timeout": 30}
        _engine = create_engine(resolved.url, future=True, connect_args=connect_args)
        _session_factory = sessionmaker(
            bind=_engine, autoflush=False, autocommit=False, future=True
        )
    return _engine


def reset_engine() -> None:
    """Reset cached SQLAlchemy engine (used in tests)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def init_db(settings: DatabaseSettings | None = None) -> None:
    """Create database tables when using SQL storage."""
    from helixos.audit.orm import AuditEventORM  # noqa: F401
    from helixos.eln import orm as eln_orm  # noqa: F401

    engine = get_engine(settings)
    if engine is not None:
        Base.metadata.create_all(engine)
        _apply_additive_migrations(engine)


def _apply_additive_migrations(engine: Engine) -> None:
    """Add newly-declared nullable columns to already-created tables.

    ``create_all`` only creates missing tables; it never alters existing ones.
    This project has no migration framework, so for backward-compatible additions
    (nullable columns) we detect and add them explicitly here. Non-nullable
    additions are skipped — those need a real migration to backfill existing rows.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    for table in Base.metadata.tables.values():
        if not isinstance(table, Table) or table.name not in existing_tables:
            continue
        present = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present or not column.nullable:
                continue
            column_type = column.type.compile(dialect=engine.dialect)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        f'ALTER TABLE "{table.name}" '
                        f'ADD COLUMN "{column.name}" {column_type}'
                    )
                )


@contextmanager
def session_scope(settings: DatabaseSettings | None = None) -> Iterator[Session]:
    """Provide a transactional SQLAlchemy session."""
    engine = get_engine(settings)
    if engine is None or _session_factory is None:
        raise RuntimeError("Database is not configured")

    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
