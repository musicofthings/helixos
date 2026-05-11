"""Pydantic schemas for ELN experiments."""

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


class ExperimentStatus(StrEnum):
    """Lifecycle states for an experiment record."""

    DRAFT = "draft"
    IN_REVIEW = "in_review"
    SIGNED = "signed"
    AMENDED = "amended"
    ARCHIVED = "archived"


class ExperimentBlockType(StrEnum):
    """Supported structured ELN block types."""

    TEXT = "text"
    TABLE = "table"
    PROTOCOL_STEPS = "protocol_steps"
    REAGENT_LIST = "reagent_list"
    SEQUENCE = "sequence"
    IMAGE = "image"
    CHART = "chart"
    AI_ANNOTATION = "ai_annotation"


class ExperimentBlock(BaseModel):
    """A structured block inside an experiment record."""

    type: ExperimentBlockType
    content: object


class ExperimentCreate(BaseModel):
    """Payload for creating an experiment draft."""

    organization_id: str
    title: str = Field(min_length=1)
    project_id: str | None = None
    blocks: list[ExperimentBlock] = Field(default_factory=list)


class Experiment(ExperimentCreate):
    """Persisted experiment representation."""

    id: str = Field(default_factory=lambda: f"exp_{uuid4().hex}")
    status: ExperimentStatus = ExperimentStatus.DRAFT
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
