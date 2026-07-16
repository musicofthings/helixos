"""Persistence contract for the ELN hierarchy."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from helixos.eln.schemas import (
    Dataset,
    Experiment,
    ExperimentVersion,
    Project,
    Sample,
    Workspace,
)


class PlateFullError(Exception):
    """Raised when an experiment already holds the maximum number of samples."""


class WellOccupiedError(Exception):
    """Raised when another sample already occupies the requested well."""


class ElnStore(Protocol):
    """Repository contract for ELN entities.

    All list/get methods that take ``organization_ids`` enforce tenant
    visibility at the storage boundary; the service layer additionally checks
    access before writes.
    """

    # Workspaces
    def create_workspace(self, workspace: Workspace) -> Workspace: ...
    def get_workspace(self, workspace_id: str) -> Workspace | None: ...
    def list_workspaces(self, organization_ids: Sequence[str]) -> list[Workspace]: ...
    def count_workspaces(self, organization_id: str) -> int: ...
    def delete_workspace(self, workspace_id: str) -> None:
        """Delete a workspace and its entire subtree (projects and below)."""
        ...

    # Projects
    def create_project(self, project: Project) -> Project: ...
    def get_project(self, project_id: str) -> Project | None: ...
    def list_projects(
        self, organization_ids: Sequence[str], workspace_id: str | None = None
    ) -> list[Project]: ...
    def update_project(self, project: Project) -> Project: ...
    def delete_project(self, project_id: str) -> None:
        """Delete a project and every experiment (and below) inside it."""
        ...

    # Experiments
    def create_experiment_with_version(
        self, experiment: Experiment, version: ExperimentVersion
    ) -> Experiment:
        """Insert an experiment and its first version in one transaction."""
        ...

    def get_experiment(self, experiment_id: str) -> Experiment | None: ...
    def list_experiments(
        self, organization_ids: Sequence[str], project_id: str | None = None
    ) -> list[Experiment]: ...
    def update_experiment(self, experiment: Experiment) -> Experiment: ...
    def delete_experiment(self, experiment_id: str) -> None:
        """Delete an experiment and its versions, samples, and datasets."""
        ...

    # Versions
    def append_version(self, version: ExperimentVersion) -> ExperimentVersion:
        """Assign the next version_number and advance HEAD, atomically.

        Callers pass a version with a placeholder ``version_number``; the store
        owns allocation so concurrent commits to one experiment cannot claim the
        same number. Returns the version as persisted.
        """
        ...

    def get_version(self, version_id: str) -> ExperimentVersion | None: ...
    def list_versions(self, experiment_id: str) -> list[ExperimentVersion]: ...
    def update_version(self, version: ExperimentVersion) -> ExperimentVersion: ...

    # Samples
    def create_sample(self, sample: Sample, max_samples: int) -> Sample:
        """Insert a sample, enforcing the plate cap and well uniqueness atomically.

        Raises PlateFullError or WellOccupiedError. Both checks must happen in the
        same transaction as the insert — checking first and inserting after lets
        concurrent writers both pass the check and overfill the plate.
        """
        ...

    def get_sample(self, sample_id: str) -> Sample | None: ...
    def list_samples(self, experiment_id: str) -> list[Sample]: ...
    def count_samples(self, experiment_id: str) -> int: ...
    def well_occupied(
        self,
        experiment_id: str,
        well_position: str,
        exclude_sample_id: str | None = None,
    ) -> bool: ...
    def update_sample(self, sample: Sample) -> Sample: ...

    # Datasets
    def create_dataset(self, dataset: Dataset) -> Dataset: ...
    def get_dataset(self, dataset_id: str) -> Dataset | None: ...
    def list_datasets(self, sample_id: str) -> list[Dataset]: ...
