"""SQLAlchemy ORM models for the ELN hierarchy."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from helixos.db.base import Base


class WorkspaceORM(Base):
    """Persisted workspace."""

    __tablename__ = "eln_workspaces"
    __table_args__ = (Index("ix_eln_workspaces_org", "organization_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ProjectORM(Base):
    """Persisted project."""

    __tablename__ = "eln_projects"
    __table_args__ = (
        Index("ix_eln_projects_org", "organization_id"),
        Index("ix_eln_projects_workspace", "workspace_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(64), nullable=False)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("eln_workspaces.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ExperimentORM(Base):
    """Persisted experiment container."""

    __tablename__ = "eln_experiments"
    __table_args__ = (
        Index("ix_eln_experiments_org", "organization_id"),
        Index("ix_eln_experiments_project", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(64), nullable=False)
    project_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("eln_projects.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    head_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version_count: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ExperimentVersionORM(Base):
    """Immutable experiment version snapshot."""

    __tablename__ = "eln_experiment_versions"
    __table_args__ = (
        UniqueConstraint(
            "experiment_id", "version_number", name="uq_eln_version_experiment_number"
        ),
        Index("ix_eln_versions_experiment", "experiment_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("eln_experiments.id"), nullable=False
    )
    organization_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False)
    parent_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    blocks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    author_subject: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class SampleORM(Base):
    """Persisted sample."""

    __tablename__ = "eln_samples"
    __table_args__ = (
        UniqueConstraint(
            "experiment_id", "well_position", name="uq_eln_sample_experiment_well"
        ),
        Index("ix_eln_samples_experiment", "experiment_id"),
        Index("ix_eln_samples_org", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(64), nullable=False)
    experiment_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("eln_experiments.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sample_type: Mapped[str] = mapped_column(String(32), nullable=False)
    well_position: Mapped[str | None] = mapped_column(String(8), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    sample_metadata: Mapped[dict] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class DatasetORM(Base):
    """Persisted dataset attached to a sample."""

    __tablename__ = "eln_datasets"
    __table_args__ = (
        Index("ix_eln_datasets_sample", "sample_id"),
        Index("ix_eln_datasets_org", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sample_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("eln_samples.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    sequence_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
