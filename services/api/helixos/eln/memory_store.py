"""In-memory ELN store for tests and no-database local development."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from datetime import datetime, timezone

from helixos.eln.schemas import (
    Dataset,
    Experiment,
    ExperimentVersion,
    Project,
    Sample,
    Workspace,
    WorkspaceInvite,
    WorkspaceShare,
)
from helixos.eln.stores import PlateFullError, WellOccupiedError


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryElnStore:
    """Thread-safe in-memory repository for the ELN hierarchy."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._workspaces: dict[str, Workspace] = {}
        self._shares: dict[str, WorkspaceShare] = {}
        self._invites: dict[str, WorkspaceInvite] = {}
        self._projects: dict[str, Project] = {}
        self._experiments: dict[str, Experiment] = {}
        self._versions: dict[str, ExperimentVersion] = {}
        self._samples: dict[str, Sample] = {}
        self._datasets: dict[str, Dataset] = {}

    # Workspaces
    def create_workspace(self, workspace: Workspace) -> Workspace:
        with self._lock:
            self._workspaces[workspace.id] = workspace
        return workspace

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        return self._workspaces.get(workspace_id)

    def list_workspaces(self, organization_ids: Sequence[str]) -> list[Workspace]:
        visible = set(organization_ids)
        items = [w for w in self._workspaces.values() if w.organization_id in visible]
        return sorted(items, key=lambda w: w.created_at)

    def count_workspaces(self, organization_id: str) -> int:
        return sum(
            1 for w in self._workspaces.values() if w.organization_id == organization_id
        )

    def delete_workspace(self, workspace_id: str) -> None:
        with self._lock:
            project_ids = [
                p.id
                for p in self._projects.values()
                if p.workspace_id == workspace_id
            ]
            for project_id in project_ids:
                self._delete_project_subtree(project_id)
                self._projects.pop(project_id, None)
            for share_id in [
                s.id for s in self._shares.values() if s.workspace_id == workspace_id
            ]:
                self._shares.pop(share_id, None)
            for invite_id in [
                i.id for i in self._invites.values() if i.workspace_id == workspace_id
            ]:
                self._invites.pop(invite_id, None)
            self._workspaces.pop(workspace_id, None)

    def create_share(self, share: WorkspaceShare) -> WorkspaceShare:
        with self._lock:
            self._shares[share.id] = share
        return share

    def get_share(self, share_id: str) -> WorkspaceShare | None:
        return self._shares.get(share_id)

    def list_shares(self, workspace_id: str) -> list[WorkspaceShare]:
        items = [s for s in self._shares.values() if s.workspace_id == workspace_id]
        return sorted(items, key=lambda s: s.created_at)

    def delete_share(self, share_id: str) -> None:
        with self._lock:
            self._shares.pop(share_id, None)

    def find_share(self, workspace_id: str, subject: str) -> WorkspaceShare | None:
        for share in self._shares.values():
            if share.workspace_id == workspace_id and share.subject == subject:
                return share
        return None

    def list_shares_for_subject(self, subject: str) -> list[WorkspaceShare]:
        items = [s for s in self._shares.values() if s.subject == subject]
        return sorted(items, key=lambda s: s.created_at)

    def update_share(self, share: WorkspaceShare) -> WorkspaceShare:
        with self._lock:
            self._shares[share.id] = share
        return share

    def create_invite(self, invite: WorkspaceInvite) -> WorkspaceInvite:
        with self._lock:
            self._invites[invite.id] = invite
        return invite

    def get_invite(self, invite_id: str) -> WorkspaceInvite | None:
        return self._invites.get(invite_id)

    def get_invite_by_token(self, token: str) -> WorkspaceInvite | None:
        for invite in self._invites.values():
            if invite.token == token:
                return invite
        return None

    def list_invites(self, workspace_id: str) -> list[WorkspaceInvite]:
        items = [i for i in self._invites.values() if i.workspace_id == workspace_id]
        return sorted(items, key=lambda i: i.created_at, reverse=True)

    def update_invite(self, invite: WorkspaceInvite) -> WorkspaceInvite:
        with self._lock:
            self._invites[invite.id] = invite
        return invite

    def accept_invite(
        self, invite: WorkspaceInvite, share: WorkspaceShare | None
    ) -> tuple[WorkspaceInvite, WorkspaceShare | None]:
        with self._lock:
            updated = invite.model_copy(
                update={"accepted_count": invite.accepted_count + 1}
            )
            self._invites[updated.id] = updated
            if share is not None:
                self._shares[share.id] = share
            return updated, share

    # Projects
    def create_project(self, project: Project) -> Project:
        with self._lock:
            self._projects[project.id] = project
        return project

    def get_project(self, project_id: str) -> Project | None:
        return self._projects.get(project_id)

    def list_projects(
        self, organization_ids: Sequence[str], workspace_id: str | None = None
    ) -> list[Project]:
        visible = set(organization_ids)
        items = [
            p
            for p in self._projects.values()
            if p.organization_id in visible
            and (workspace_id is None or p.workspace_id == workspace_id)
        ]
        return sorted(items, key=lambda p: p.created_at)

    def update_project(self, project: Project) -> Project:
        with self._lock:
            self._projects[project.id] = project
        return project

    def delete_project(self, project_id: str) -> None:
        with self._lock:
            self._delete_project_subtree(project_id)
            self._projects.pop(project_id, None)

    # Experiments
    def create_experiment_with_version(
        self, experiment: Experiment, version: ExperimentVersion
    ) -> Experiment:
        with self._lock:
            self._experiments[experiment.id] = experiment
            self._versions[version.id] = version
        return experiment

    def get_experiment(self, experiment_id: str) -> Experiment | None:
        return self._experiments.get(experiment_id)

    def list_experiments(
        self, organization_ids: Sequence[str], project_id: str | None = None
    ) -> list[Experiment]:
        visible = set(organization_ids)
        items = [
            e
            for e in self._experiments.values()
            if e.organization_id in visible
            and (project_id is None or e.project_id == project_id)
        ]
        return sorted(items, key=lambda e: e.created_at)

    def update_experiment(self, experiment: Experiment) -> Experiment:
        with self._lock:
            self._experiments[experiment.id] = experiment
        return experiment

    def delete_experiment(self, experiment_id: str) -> None:
        with self._lock:
            self._delete_experiment_subtree(experiment_id)

    def _delete_project_subtree(self, project_id: str) -> None:
        # Caller holds the lock. Removes every experiment (and its versions,
        # samples, datasets) under the project, but not the project row itself.
        experiment_ids = [
            e.id
            for e in self._experiments.values()
            if e.project_id == project_id
        ]
        for experiment_id in experiment_ids:
            self._delete_experiment_subtree(experiment_id)

    def _delete_experiment_subtree(self, experiment_id: str) -> None:
        # Caller holds the lock.
        sample_ids = [
            s.id
            for s in self._samples.values()
            if s.experiment_id == experiment_id
        ]
        for sample_id in sample_ids:
            for dataset_id in [
                d.id for d in self._datasets.values() if d.sample_id == sample_id
            ]:
                self._datasets.pop(dataset_id, None)
            self._samples.pop(sample_id, None)
        for version_id in [
            v.id for v in self._versions.values() if v.experiment_id == experiment_id
        ]:
            self._versions.pop(version_id, None)
        self._experiments.pop(experiment_id, None)

    # Versions
    def append_version(self, version: ExperimentVersion) -> ExperimentVersion:
        # Allocate the number and advance HEAD under one lock, so two concurrent
        # commits to the same experiment cannot claim the same version_number.
        with self._lock:
            next_number = (
                max(
                    (
                        v.version_number
                        for v in self._versions.values()
                        if v.experiment_id == version.experiment_id
                    ),
                    default=0,
                )
                + 1
            )
            stored = version.model_copy(update={"version_number": next_number})
            self._versions[stored.id] = stored

            experiment = self._experiments.get(stored.experiment_id)
            if experiment is not None:
                self._experiments[experiment.id] = experiment.model_copy(
                    update={
                        "head_version_id": stored.id,
                        "version_count": next_number,
                        "updated_at": _now(),
                    }
                )
        return stored

    def get_version(self, version_id: str) -> ExperimentVersion | None:
        return self._versions.get(version_id)

    def list_versions(self, experiment_id: str) -> list[ExperimentVersion]:
        items = [v for v in self._versions.values() if v.experiment_id == experiment_id]
        return sorted(items, key=lambda v: v.version_number)

    def update_version(self, version: ExperimentVersion) -> ExperimentVersion:
        with self._lock:
            self._versions[version.id] = version
        return version

    # Samples
    def create_sample(self, sample: Sample, max_samples: int) -> Sample:
        # Cap check, well check and insert under one lock: doing them separately
        # lets two concurrent creates both observe 95 samples and overfill the plate.
        with self._lock:
            siblings = [
                s
                for s in self._samples.values()
                if s.experiment_id == sample.experiment_id
            ]
            if len(siblings) >= max_samples:
                raise PlateFullError
            if sample.well_position is not None and any(
                s.well_position == sample.well_position for s in siblings
            ):
                raise WellOccupiedError
            self._samples[sample.id] = sample
        return sample

    def get_sample(self, sample_id: str) -> Sample | None:
        return self._samples.get(sample_id)

    def list_samples(self, experiment_id: str) -> list[Sample]:
        items = [s for s in self._samples.values() if s.experiment_id == experiment_id]
        return sorted(items, key=lambda s: s.created_at)

    def count_samples(self, experiment_id: str) -> int:
        return sum(
            1 for s in self._samples.values() if s.experiment_id == experiment_id
        )

    def well_occupied(
        self,
        experiment_id: str,
        well_position: str,
        exclude_sample_id: str | None = None,
    ) -> bool:
        for sample in self._samples.values():
            if sample.experiment_id != experiment_id:
                continue
            if sample.id == exclude_sample_id:
                continue
            if sample.well_position == well_position:
                return True
        return False

    def update_sample(self, sample: Sample) -> Sample:
        with self._lock:
            self._samples[sample.id] = sample
        return sample

    def delete_sample(self, sample_id: str) -> None:
        with self._lock:
            for dataset_id in [
                d.id for d in self._datasets.values() if d.sample_id == sample_id
            ]:
                self._datasets.pop(dataset_id, None)
            self._samples.pop(sample_id, None)

    # Datasets
    def create_dataset(self, dataset: Dataset) -> Dataset:
        with self._lock:
            self._datasets[dataset.id] = dataset
        return dataset

    def get_dataset(self, dataset_id: str) -> Dataset | None:
        return self._datasets.get(dataset_id)

    def list_datasets(self, sample_id: str) -> list[Dataset]:
        items = [d for d in self._datasets.values() if d.sample_id == sample_id]
        return sorted(items, key=lambda d: d.created_at)
