"""Database configuration."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DatabaseSettings:
    """Environment-driven database configuration."""

    url: str | None

    @classmethod
    def from_env(cls) -> "DatabaseSettings":
        url = os.getenv("HELIX_DATABASE_URL") or os.getenv("DATABASE_URL")
        if url is not None and not url.strip():
            url = None
        return cls(url=url)

    @property
    def is_configured(self) -> bool:
        return bool(self.url)

    @property
    def backend(self) -> str:
        if not self.url:
            return "memory"
        if self.url.startswith("sqlite"):
            return "sqlite"
        if self.url.startswith("postgresql"):
            return "postgresql"
        return "sql"


def get_database_settings() -> DatabaseSettings:
    """Load database settings from the current process environment."""
    return DatabaseSettings.from_env()


# Snapshot at import time for modules that read settings once during startup.
database_settings = get_database_settings()
