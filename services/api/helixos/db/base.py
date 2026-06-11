"""SQLAlchemy base metadata."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for HelixOS ORM models."""
