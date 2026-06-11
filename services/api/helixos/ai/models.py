"""In-memory models for AI sessions and runs."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4


class AgentRunStatus(StrEnum):
    """Lifecycle states for an agent run."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentSessionRecord:
    """Persisted agent conversation session."""

    id: str
    organization_id: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, organization_id: str) -> "AgentSessionRecord":
        now = datetime.now(timezone.utc)
        return cls(
            id=f"sess_{uuid4().hex}",
            organization_id=organization_id,
            created_at=now,
            updated_at=now,
        )


@dataclass
class AgentRunRecord:
    """Execution record for a single agent turn."""

    id: str
    session_id: str
    status: AgentRunStatus
    message: str
    created_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    events: list[dict[str, object]] = field(default_factory=list)

    @classmethod
    def create(cls, session_id: str, message: str) -> "AgentRunRecord":
        return cls(
            id=f"run_{uuid4().hex}",
            session_id=session_id,
            status=AgentRunStatus.QUEUED,
            message=message,
            created_at=datetime.now(timezone.utc),
        )
