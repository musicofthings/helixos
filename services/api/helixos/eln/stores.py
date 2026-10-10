"""Persistence contract for the ELN hierarchy."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Generic, TypeVar
from typing import Protocol as TypingProtocol

from helixos.eln.schemas import (
    Dataset,
    Experiment,
    ExperimentStatus,
    ExperimentVersion,
    Project,
    Protocol,
    Sample,
    Workspace,
    WorkspaceInvite,
    WorkspaceShare,
)


T = TypeVar("T")


@dataclass(frozen=True)
class PageRequest:
    """A window over an ordered result set."""

    limit: int
    offset: int = 0


@dataclass
class PageResult(Generic[T]):
    """One page of items plus the size of the full (unpaged) result set."""

    items: list[T] = field(default_factory=list)
    total: int = 0


class PlateFullError(Exception):
    """Raised when an experiment already holds the maximum number of samples."""


class StaleStateError(Exception):
    """Raised when a compare-and-swap write finds the row changed underneath it."""


class InviteUnavailableError(Exception):
    """Raised when an invite is expired, revoked, or out of uses at accept time."""


class WellOccupiedError(Exception):
    """Raised when another sample already occupies the requested well."""


class ElnStore(TypingProtocol):
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
    def page_workspaces(
        self,
        organization_ids: Sequence[str],
        shared_workspace_ids: Sequence[str],
        page: PageRequest | None = None,
    ) -> PageResult[Workspace]:
        """Workspaces in ``organization_ids`` or listed in ``shared_workspace_ids``.

        Ordered by (created_at, id); ``page=None`` returns everything.
        """
        ...
    def delete_workspace(self, workspace_id: str) -> None:
        """Delete a workspace and its entire subtree (projects and below)."""
        ...

    # Workspace collaboration
    def create_share(self, share: WorkspaceShare) -> WorkspaceShare: ...
    def get_share(self, share_id: str) -> WorkspaceShare | None: ...
    def list_shares(self, workspace_id: str) -> list[WorkspaceShare]: ...
    def delete_share(self, share_id: str) -> None: ...
    def find_share(
        self, workspace_id: str, subject: str
    ) -> WorkspaceShare | None: ...
    def list_shares_for_subject(self, subject: str) -> list[WorkspaceShare]: ...
    def update_share(self, share: WorkspaceShare) -> WorkspaceShare: ...

    def create_invite(self, invite: WorkspaceInvite) -> WorkspaceInvite: ...
    def get_invite(self, invite_id: str) -> WorkspaceInvite | None: ...
    def get_invite_by_token(self, token: str) -> WorkspaceInvite | None: ...
    def list_invites(self, workspace_id: str) -> list[WorkspaceInvite]: ...
    def update_invite(self, invite: WorkspaceInvite) -> WorkspaceInvite: ...
    def accept_invite(
        self, invite: WorkspaceInvite, share: WorkspaceShare | None
    ) -> tuple[WorkspaceInvite, WorkspaceShare | None]:
        """Atomically re-check invite activity, bump the count and insert the share.

        Raises ``InviteUnavailableError`` if the invite is no longer active.
        """
        ...

    # Projects
    def create_project(self, project: Project) -> Project: ...
    def get_project(self, project_id: str) -> Project | None: ...
    def list_projects(
        self, organization_ids: Sequence[str], workspace_id: str | None = None
    ) -> list[Project]: ...
    def page_projects(
        self,
        organization_ids: Sequence[str],
        shared_workspace_ids: Sequence[str] = (),
        workspace_id: str | None = None,
        page: PageRequest | None = None,
    ) -> PageResult[Project]:
        """Projects in ``organization_ids`` or in a shared workspace."""
        ...

    def project_ids_in_workspaces(self, workspace_ids: Sequence[str]) -> list[str]: ...
    def update_project(self, project: Project) -> Project: ...
    def delete_project(self, project_id: str) -> None:
        """Delete a project and every experiment (and below) inside it."""
        ...

    # Protocols
    def create_protocol(self, protocol: Protocol) -> Protocol: ...
    def get_protocol(self, protocol_id: str) -> Protocol | None: ...
    def list_protocols(
        self, organization_ids: Sequence[str], workspace_id: str | None = None
    ) -> list[Protocol]: ...
    def page_protocols(
        self,
        organization_ids: Sequence[str],
        shared_workspace_ids: Sequence[str] = (),
        workspace_id: str | None = None,
        page: PageRequest | None = None,
    ) -> PageResult[Protocol]: ...
    def update_protocol(self, protocol: Protocol) -> Protocol: ...
    def delete_protocol(self, protocol_id: str) -> None: ...

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
    def page_experiments(
        self,
        organization_ids: Sequence[str],
        shared_project_ids: Sequence[str] = (),
        project_id: str | None = None,
        page: PageRequest | None = None,
    ) -> PageResult[Experiment]:
        """Experiments in ``organization_ids`` or in a shared project."""
        ...

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
    def page_versions(
        self, experiment_id: str, page: PageRequest | None = None
    ) -> PageResult[ExperimentVersion]: ...
    def update_version(
        self, version: ExperimentVersion, expected_status: ExperimentStatus
    ) -> ExperimentVersion:
        """Persist ``version.status`` only if the stored status is still ``expected_status``.

        Raises ``StaleStateError`` when another request changed it first.
        """
        ...

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
    def page_samples(
        self, experiment_id: str, page: PageRequest | None = None
    ) -> PageResult[Sample]: ...
    def count_samples(self, experiment_id: str) -> int: ...
    def well_occupied(
        self,
        experiment_id: str,
        well_position: str,
        exclude_sample_id: str | None = None,
    ) -> bool: ...
    def update_sample(self, sample: Sample) -> Sample: ...
    def delete_sample(self, sample_id: str) -> None:
        """Delete a sample and every dataset attached to it."""
        ...

    # Datasets
    def create_dataset(self, dataset: Dataset) -> Dataset: ...
    def get_dataset(self, dataset_id: str) -> Dataset | None: ...
    def list_datasets(self, sample_id: str) -> list[Dataset]: ...
    def page_datasets(
        self, sample_id: str, page: PageRequest | None = None
    ) -> PageResult[Dataset]: ...
