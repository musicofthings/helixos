"""Database engine and session helpers."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

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
        connect_args = {"check_same_thread": False} if resolved.url.startswith("sqlite") else {}
        _engine = create_engine(resolved.url, future=True, connect_args=connect_args)
        _session_factory = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
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

    engine = get_engine(settings)
    if engine is not None:
        Base.metadata.create_all(engine)


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
