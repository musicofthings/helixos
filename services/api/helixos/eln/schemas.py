"""Pydantic schemas for the ELN domain hierarchy.

Hierarchy: Workspace -> Project -> Experiment -> ExperimentVersion
                 |                     \-> Sample -> Dataset
                 └─ Protocol (reusable procedure library)

Experiments are versioned like a source repository: each edit creates an
immutable ExperimentVersion ("commit") with a parent pointer, and the
experiment tracks the current HEAD version.
"""

import secrets
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

MAX_SAMPLES_PER_EXPERIMENT = 96
PLATE_ROWS = "ABCDEFGH"
PLATE_COLUMNS = 12


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class WorkspaceCategory(StrEnum):
    """Scientific category a workspace organizes work under.

    Some categories carry a further ``subcategory`` refinement (see
    ``CATEGORY_SUBCATEGORIES``); the subcategory itself is stored as a free
    string so labs can extend the suggested lists (e.g. new Programmable Bio
    assays) without a schema change.
    """

    MOLECULAR_BIOLOGY = "molecular_biology"
    BIOCHEMISTRY = "biochemistry"
    MICROBIOLOGY = "microbiology"
    NEXT_GEN_SEQUENCING = "next_gen_sequencing"
    DIGITAL_PATHOLOGY = "digital_pathology"
    PROGRAMMABLE_BIO = "programmable_bio"
    # Retained so workspaces persisted under the earlier taxonomy still load.
    GENOMICS = "genomics"
    CELL_BIOLOGY = "cell_biology"
    CUSTOM = "custom"


# Suggested subcategories surfaced in the create-workspace form. Not enforced by
# the API: the list is advisory, and labs may store any subcategory string.
CATEGORY_SUBCATEGORIES: dict[WorkspaceCategory, tuple[str, ...]] = {
    WorkspaceCategory.NEXT_GEN_SEQUENCING: ("DNA", "RNA", "Protein"),
    WorkspaceCategory.DIGITAL_PATHOLOGY: ("Cells", "Tissues"),
    WorkspaceCategory.PROGRAMMABLE_BIO: (
        "Single-cell experiments",
        "PerturbGen",
        "Protein-protein interaction studies",
    ),
}


class ProjectStatus(StrEnum):
    """Lifecycle states for a project."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class ExperimentStatus(StrEnum):
    """Lifecycle states for an experiment version."""

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


class SampleType(StrEnum):
    """Biological or chemical nature of a sample."""

    DNA = "dna"
    RNA = "rna"
    PROTEIN = "protein"
    CELL = "cell"
    TISSUE = "tissue"
    REAGENT = "reagent"
    OTHER = "other"


class SampleStatus(StrEnum):
    """Lifecycle states for a sample."""

    PLANNED = "planned"
    ACTIVE = "active"
    CONSUMED = "consumed"
    ARCHIVED = "archived"


class DatasetType(StrEnum):
    """Kind of data captured on a sample."""

    DNA_SEQUENCE = "dna_sequence"
    RNA_SEQUENCE = "rna_sequence"
    PROTEIN_SEQUENCE = "protein_sequence"
    MEASUREMENT = "measurement"
    FILE = "file"
    OTHER = "other"


class WorkspaceShareRole(StrEnum):
    """Collaboration role on a shared workspace."""

    VIEWER = "viewer"
    EDITOR = "editor"


class ExperimentBlock(BaseModel):
    """A structured block inside an experiment version."""

    type: ExperimentBlockType
    content: object


# --------------------------------------------------------------------------- #
# Workspace
# --------------------------------------------------------------------------- #
class WorkspaceCreate(BaseModel):
    """Payload for creating a workspace."""

    organization_id: str
    name: str = Field(min_length=1)
    category: WorkspaceCategory = WorkspaceCategory.CUSTOM
    subcategory: str | None = Field(default=None, max_length=64)
    description: str | None = None


class Workspace(WorkspaceCreate):
    """Persisted workspace."""

    id: str = Field(default_factory=lambda: f"ws_{uuid4().hex}")
    is_default: bool = False
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


# --------------------------------------------------------------------------- #
# Workspace collaboration (shares + invites)
# --------------------------------------------------------------------------- #
class WorkspaceShareCreate(BaseModel):
    """Payload for granting a collaborator access to a workspace."""

    subject: str = Field(min_length=1, max_length=128)
    role: WorkspaceShareRole = WorkspaceShareRole.VIEWER


class WorkspaceShareUpdate(BaseModel):
    """Payload for updating a collaborator grant's role."""

    role: WorkspaceShareRole


class WorkspaceShare(BaseModel):
    """Persisted collaborator grant on a workspace."""

    id: str = Field(default_factory=lambda: f"wss_{uuid4().hex}")
    workspace_id: str
    organization_id: str
    subject: str
    role: WorkspaceShareRole
    granted_by: str
    created_at: datetime = Field(default_factory=_now)


class WorkspaceInviteCreate(BaseModel):
    """Payload for creating a workspace invite link."""

    role: WorkspaceShareRole = WorkspaceShareRole.VIEWER
    expires_in_hours: int = Field(default=168, ge=1, le=8760)
    max_uses: int | None = Field(default=None, ge=1, le=10_000)


class WorkspaceInvite(BaseModel):
    """Persisted invite link for a workspace.

    ``token`` is returned only on create; list/collaboration responses redact it.
    """

    id: str = Field(default_factory=lambda: f"wsi_{uuid4().hex}")
    workspace_id: str
    organization_id: str
    token: str | None = Field(default_factory=lambda: secrets.token_urlsafe(32))
    role: WorkspaceShareRole
    created_by: str
    expires_at: datetime
    revoked_at: datetime | None = None
    accepted_count: int = 0
    max_uses: int | None = None
    created_at: datetime = Field(default_factory=_now)

    @field_validator("expires_at", "revoked_at", "created_at", mode="before")
    @classmethod
    def _ensure_aware(cls, value: object) -> object:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        if self.max_uses is not None and self.accepted_count >= self.max_uses:
            return False
        return self.expires_at >= _now()


class WorkspaceCollaboration(BaseModel):
    """Bundle of grants and invites for a workspace share panel."""

    shares: list[WorkspaceShare] = Field(default_factory=list)
    invites: list[WorkspaceInvite] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Project
# --------------------------------------------------------------------------- #
class ProjectCreate(BaseModel):
    """Payload for creating a project."""

    organization_id: str
    workspace_id: str
    name: str = Field(min_length=1)
    description: str | None = None


class ProjectUpdate(BaseModel):
    """Payload for updating a project's mutable fields."""

    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    status: ProjectStatus | None = None


class Project(ProjectCreate):
    """Persisted project."""

    id: str = Field(default_factory=lambda: f"proj_{uuid4().hex}")
    status: ProjectStatus = ProjectStatus.ACTIVE
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


# --------------------------------------------------------------------------- #
# Protocol library (workspace-scoped)
# --------------------------------------------------------------------------- #
class ProtocolStatus(StrEnum):
    """Lifecycle states for a reusable protocol."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class ProtocolSourceProvider(StrEnum):
    """Where a protocol originated."""

    MANUAL = "manual"
    PROTOCOLS_IO = "protocols_io"
    URL = "url"


class ProtocolStep(BaseModel):
    """One ordered step in a protocol."""

    order: int = Field(ge=1)
    title: str = Field(min_length=1)
    body: str = ""


class ProtocolCreate(BaseModel):
    """Payload for creating a protocol in a workspace library."""

    organization_id: str
    workspace_id: str
    name: str = Field(min_length=1)
    description: str | None = None
    steps: list[ProtocolStep] = Field(default_factory=list)
    source_provider: ProtocolSourceProvider = ProtocolSourceProvider.MANUAL
    source_url: str | None = None
    source_external_id: str | None = None


class ProtocolUpdate(BaseModel):
    """Payload for updating a protocol's mutable fields."""

    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    status: ProtocolStatus | None = None
    steps: list[ProtocolStep] | None = None


class Protocol(ProtocolCreate):
    """Persisted reusable protocol."""

    id: str = Field(default_factory=lambda: f"prot_{uuid4().hex}")
    status: ProtocolStatus = ProtocolStatus.DRAFT
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class ProtocolImportRequest(BaseModel):
    """Import a protocol shell from an external source (stubbed fetch)."""

    organization_id: str
    workspace_id: str
    source_provider: ProtocolSourceProvider = ProtocolSourceProvider.PROTOCOLS_IO
    source_url: str | None = None
    source_external_id: str | None = None
    name: str | None = Field(default=None, min_length=1)


# --------------------------------------------------------------------------- #
# Experiment + versions
# --------------------------------------------------------------------------- #
class ExperimentCreate(BaseModel):
    """Payload for creating an experiment and its first version."""

    organization_id: str
    project_id: str | None = None
    name: str = Field(min_length=1)
    description: str | None = None
    blocks: list[ExperimentBlock] = Field(default_factory=list)


class Experiment(BaseModel):
    """Persisted experiment container that tracks a HEAD version."""

    id: str = Field(default_factory=lambda: f"exp_{uuid4().hex}")
    organization_id: str
    project_id: str | None = None
    name: str
    description: str | None = None
    head_version_id: str | None = None
    version_count: int = 0
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class ExperimentVersionCreate(BaseModel):
    """Payload for committing a new experiment version."""

    message: str = Field(min_length=1)
    blocks: list[ExperimentBlock] = Field(default_factory=list)
    parent_version_id: str | None = None


class ExperimentVersion(BaseModel):
    """Immutable snapshot ("commit") of an experiment's content."""

    id: str = Field(default_factory=lambda: f"expv_{uuid4().hex}")
    experiment_id: str
    organization_id: str
    version_number: int
    parent_version_id: str | None = None
    message: str
    status: ExperimentStatus = ExperimentStatus.DRAFT
    blocks: list[ExperimentBlock] = Field(default_factory=list)
    author_subject: str
    created_at: datetime = Field(default_factory=_now)


class ExperimentStatusUpdate(BaseModel):
    """Payload for transitioning an experiment version's status."""

    status: ExperimentStatus


# --------------------------------------------------------------------------- #
# Sample
# --------------------------------------------------------------------------- #
class SampleCreate(BaseModel):
    """Payload for creating a sample under an experiment."""

    organization_id: str
    experiment_id: str
    name: str = Field(min_length=1)
    sample_type: SampleType = SampleType.OTHER
    well_position: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class SampleUpdate(BaseModel):
    """Payload for updating a sample's mutable fields."""

    name: str | None = Field(default=None, min_length=1)
    sample_type: SampleType | None = None
    well_position: str | None = None
    status: SampleStatus | None = None
    metadata: dict[str, object] | None = None


class Sample(BaseModel):
    """Persisted sample."""

    id: str = Field(default_factory=lambda: f"smp_{uuid4().hex}")
    organization_id: str
    experiment_id: str
    name: str
    sample_type: SampleType = SampleType.OTHER
    well_position: str | None = None
    status: SampleStatus = SampleStatus.PLANNED
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


# --------------------------------------------------------------------------- #
# Dataset
# --------------------------------------------------------------------------- #
class DatasetCreate(BaseModel):
    """Payload for attaching a dataset to a sample."""

    organization_id: str
    sample_id: str
    name: str = Field(min_length=1)
    dataset_type: DatasetType = DatasetType.OTHER
    sequence_id: str | None = None
    content: dict[str, object] = Field(default_factory=dict)


class Dataset(BaseModel):
    """Persisted dataset attached to a sample."""

    id: str = Field(default_factory=lambda: f"ds_{uuid4().hex}")
    organization_id: str
    sample_id: str
    name: str
    dataset_type: DatasetType = DatasetType.OTHER
    sequence_id: str | None = None
    content: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


def normalize_well_position(value: str) -> str | None:
    """Validate and normalize a 96-well plate coordinate like 'A1' or 'h12'.

    Returns the normalized upper-case coordinate, or None when the input does
    not name a valid well on an 8x12 plate.
    """
    candidate = value.strip().upper()
    if len(candidate) < 2:
        return None
    row = candidate[0]
    col_part = candidate[1:]
    if row not in PLATE_ROWS or not col_part.isdigit():
        return None
    column = int(col_part)
    if column < 1 or column > PLATE_COLUMNS:
        return None
    return f"{row}{column}"
