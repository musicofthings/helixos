"""Pydantic schemas for molecular biology records."""

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class MoleculeType(StrEnum):
    """Supported biological molecule types."""

    DNA = "dna"
    RNA = "rna"
    PROTEIN = "protein"


class Topology(StrEnum):
    """Supported molecular topologies."""

    LINEAR = "linear"
    CIRCULAR = "circular"


class SequenceFeature(BaseModel):
    """Annotated region on a biological sequence."""

    name: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    kind: str


class Sequence(BaseModel):
    """Sequence metadata returned by the molecular module."""

    id: str
    organization_id: str
    name: str
    molecule_type: MoleculeType
    topology: Topology
    length: int = Field(ge=0)
    features: list[SequenceFeature] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
