"""Database engine and session helpers."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
import random
import time
from typing import TypeVar

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from helixos.db.settings import DatabaseSettings, get_database_settings

T = TypeVar("T")

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_migrated_engine: Engine | None = None


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
        if resolved.url.startswith("sqlite"):
            # SQLite ignores FOREIGN KEY constraints unless enabled per connection.
            @event.listens_for(_engine, "connect")
            def _enable_sqlite_foreign_keys(dbapi_connection, _record) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        _session_factory = sessionmaker(
            bind=_engine, autoflush=False, autocommit=False, future=True
        )
    return _engine


def reset_engine() -> None:
    """Reset cached SQLAlchemy engine (used in tests)."""
    global _engine, _session_factory, _migrated_engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    _migrated_engine = None


def init_db(settings: DatabaseSettings | None = None) -> None:
    """Bring the database schema up to date (idempotent; runs once per engine)."""
    global _migrated_engine
    from helixos.db.migrations import upgrade

    engine = get_engine(settings)
    if engine is None or _migrated_engine is engine:
        return
    upgrade(engine)
    _migrated_engine = engine


# Ambient session shared by every store call made inside ``unit_of_work``.
_ambient_session: ContextVar[Session | None] = ContextVar("helix_ambient_session", default=None)


def in_unit_of_work() -> bool:
    """True when the caller is inside an active ``unit_of_work``."""
    return _ambient_session.get() is not None


@contextmanager
def unit_of_work(settings: DatabaseSettings | None = None) -> Iterator[Session | None]:
    """Run several store calls in one transaction.

    Inside the block, ``session_scope`` joins this session instead of committing,
    so a domain mutation and its audit event commit or roll back together.
    Nested blocks join the outer transaction. Without a configured database
    (in-memory stores) this is a no-op.
    """
    if _ambient_session.get() is not None:
        yield _ambient_session.get()
        return
    engine = get_engine(settings)
    if engine is None or _session_factory is None:
        yield None
        return

    session = _session_factory()
    token = _ambient_session.set(session)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        _ambient_session.reset(token)
        session.close()


def run_atomic(
    operation: Callable[[], T],
    *,
    attempts: int = 12,
    backoff_base: float = 0.01,
    backoff_max: float = 0.25,
) -> T:
    """Run ``operation`` in a unit of work, retrying the whole transaction on
    transient write conflicts (audit chain-head collisions, busy SQLite writer).

    Nested calls join the outer transaction and never retry on their own.
    """
    if in_unit_of_work():
        return operation()
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with unit_of_work():
                return operation()
        except (IntegrityError, OperationalError) as exc:
            last_error = exc
            time.sleep(random.uniform(0, min(backoff_base * (2**attempt), backoff_max)))
    raise RuntimeError("Transaction failed after retries") from last_error


@contextmanager
def session_scope(settings: DatabaseSettings | None = None) -> Iterator[Session]:
    """Provide a transactional SQLAlchemy session (joins the ambient one if any)."""
    ambient = _ambient_session.get()
    if ambient is not None:
        yield ambient
        ambient.flush()
        return

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
