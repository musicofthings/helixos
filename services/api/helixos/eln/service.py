"""Application service for the ELN hierarchy.

Coordinates workspaces, projects, experiments (with git-style versioning),
samples (96-well plate constrained), and datasets. Every mutation is tenant
scoped and recorded to the audit trail.
"""

from __future__ import annotations

from datetime import datetime, timezone

from helixos.audit.service import audit_service
from helixos.auth.schemas import Actor
from helixos.auth.service import organization_service
from helixos.db.settings import DatabaseSettings, get_database_settings
from helixos.eln.memory_store import MemoryElnStore
from helixos.eln.schemas import (
    MAX_SAMPLES_PER_EXPERIMENT,
    Dataset,
    DatasetCreate,
    Experiment,
    ExperimentCreate,
    ExperimentStatus,
    ExperimentStatusUpdate,
    ExperimentVersion,
    ExperimentVersionCreate,
    Project,
    ProjectCreate,
    ProjectUpdate,
    Sample,
    SampleCreate,
    SampleUpdate,
    Workspace,
    WorkspaceCategory,
    WorkspaceCreate,
    normalize_well_position,
)
from helixos.eln.stores import ElnStore, PlateFullError, WellOccupiedError
from helixos.errors import api_error

_ALLOWED_STATUS_TRANSITIONS: frozenset[tuple[ExperimentStatus, ExperimentStatus]] = (
    frozenset(
        {
            (ExperimentStatus.DRAFT, ExperimentStatus.IN_REVIEW),
            (ExperimentStatus.IN_REVIEW, ExperimentStatus.DRAFT),
            (ExperimentStatus.IN_REVIEW, ExperimentStatus.SIGNED),
        }
    )
)

DEFAULT_WORKSPACES: tuple[tuple[str, WorkspaceCategory, str], ...] = (
    (
        "Molecular Biology",
        WorkspaceCategory.MOLECULAR_BIOLOGY,
        "Cloning, PCR, sequencing, and construct design.",
    ),
    (
        "Biochemistry",
        WorkspaceCategory.BIOCHEMISTRY,
        "Protein purification, assays, and enzyme kinetics.",
    ),
    (
        "Microbiology",
        WorkspaceCategory.MICROBIOLOGY,
        "Strain culture, plating, and phenotyping.",
    ),
)


def build_eln_store(settings: DatabaseSettings | None = None) -> ElnStore:
    """Create the configured ELN store backend."""
    resolved = settings or get_database_settings()
    if resolved.is_configured:
        from helixos.db.session import init_db
        from helixos.eln.sql_store import SqlElnStore

        init_db(resolved)
        return SqlElnStore()
    return MemoryElnStore()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ElnService:
    """Coordinates the workspace -> project -> experiment -> sample -> dataset tree."""

    def __init__(self, store: ElnStore | None = None) -> None:
        self._store = store or build_eln_store()

    def use_store(self, store: ElnStore) -> None:
        """Replace the active store backend (used in tests)."""
        self._store = store

    # ----------------------------------------------------------------- #
    # Workspaces
    # ----------------------------------------------------------------- #
    def ensure_default_workspaces(
        self, organization_id: str, actor: Actor
    ) -> list[Workspace]:
        """Seed the default workspace set for an organization if it has none."""
        organization_service.require_access(actor, organization_id)
        if self._store.count_workspaces(organization_id) > 0:
            return self._store.list_workspaces([organization_id])

        created: list[Workspace] = []
        for name, category, description in DEFAULT_WORKSPACES:
            workspace = Workspace(
                organization_id=organization_id,
                name=name,
                category=category,
                description=description,
                is_default=True,
            )
            self._store.create_workspace(workspace)
            created.append(workspace)
        audit_service.record(
            organization_id=organization_id,
            actor=actor,
            event_type="eln.workspaces_seeded",
            resource_type="workspace",
            resource_id=organization_id,
            payload={"count": len(created)},
        )
        return created

    def create_workspace(self, payload: WorkspaceCreate, actor: Actor) -> Workspace:
        organization_service.require_access(actor, payload.organization_id)
        workspace = Workspace(**payload.model_dump())
        self._store.create_workspace(workspace)
        audit_service.record(
            organization_id=workspace.organization_id,
            actor=actor,
            event_type="eln.workspace_created",
            resource_type="workspace",
            resource_id=workspace.id,
            payload={"name": workspace.name, "category": workspace.category.value},
        )
        return workspace

    def list_workspaces(
        self, actor: Actor, organization_id: str | None = None
    ) -> list[Workspace]:
        organization_ids = self._visible_org_ids(actor, organization_id)
        return self._store.list_workspaces(organization_ids)

    def get_workspace(self, workspace_id: str, actor: Actor) -> Workspace:
        workspace = self._store.get_workspace(workspace_id)
        if workspace is None:
            raise _not_found("workspace", workspace_id)
        organization_service.require_access(actor, workspace.organization_id)
        return workspace

    # ----------------------------------------------------------------- #
    # Projects
    # ----------------------------------------------------------------- #
    def create_project(self, payload: ProjectCreate, actor: Actor) -> Project:
        organization_service.require_access(actor, payload.organization_id)
        workspace = self._store.get_workspace(payload.workspace_id)
        if workspace is None or workspace.organization_id != payload.organization_id:
            raise _not_found("workspace", payload.workspace_id)
        project = Project(**payload.model_dump())
        self._store.create_project(project)
        audit_service.record(
            organization_id=project.organization_id,
            actor=actor,
            event_type="eln.project_created",
            resource_type="project",
            resource_id=project.id,
            payload={"name": project.name, "workspace_id": project.workspace_id},
        )
        return project

    def list_projects(
        self,
        actor: Actor,
        organization_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[Project]:
        organization_ids = self._visible_org_ids(actor, organization_id)
        return self._store.list_projects(organization_ids, workspace_id=workspace_id)

    def get_project(self, project_id: str, actor: Actor) -> Project:
        project = self._store.get_project(project_id)
        if project is None:
            raise _not_found("project", project_id)
        organization_service.require_access(actor, project.organization_id)
        return project

    def update_project(
        self, project_id: str, payload: ProjectUpdate, actor: Actor
    ) -> Project:
        project = self.get_project(project_id, actor)
        updates = payload.model_dump(exclude_unset=True)
        _reject_null_updates(updates, _PROJECT_REQUIRED_FIELDS)
        if not updates:
            return project
        updated = project.model_copy(update={**updates, "updated_at": _now()})
        self._store.update_project(updated)
        audit_service.record(
            organization_id=updated.organization_id,
            actor=actor,
            event_type="eln.project_updated",
            resource_type="project",
            resource_id=updated.id,
            payload={"fields": sorted(updates.keys())},
        )
        return updated

    # ----------------------------------------------------------------- #
    # Experiments + versions
    # ----------------------------------------------------------------- #
    def create_experiment(self, payload: ExperimentCreate, actor: Actor) -> Experiment:
        """Create an experiment and its initial draft version (v1)."""
        organization_service.require_access(actor, payload.organization_id)
        if payload.project_id is not None:
            project = self._store.get_project(payload.project_id)
            if project is None or project.organization_id != payload.organization_id:
                raise _not_found("project", payload.project_id)

        experiment = Experiment(
            organization_id=payload.organization_id,
            project_id=payload.project_id,
            name=payload.name,
            description=payload.description,
        )
        version = ExperimentVersion(
            experiment_id=experiment.id,
            organization_id=experiment.organization_id,
            version_number=1,
            parent_version_id=None,
            message="Initial version",
            status=ExperimentStatus.DRAFT,
            blocks=payload.blocks,
            author_subject=actor.subject,
        )
        experiment = experiment.model_copy(
            update={"head_version_id": version.id, "version_count": 1}
        )
        # Single transaction: an experiment must never exist without its v1.
        self._store.create_experiment_with_version(experiment, version)

        audit_service.record(
            organization_id=experiment.organization_id,
            actor=actor,
            event_type="eln.experiment_created",
            resource_type="experiment",
            resource_id=experiment.id,
            payload={"name": experiment.name, "version_id": version.id},
        )
        return experiment

    def list_experiments(
        self,
        actor: Actor,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> list[Experiment]:
        organization_ids = self._visible_org_ids(actor, organization_id)
        return self._store.list_experiments(organization_ids, project_id=project_id)

    def get_experiment(self, experiment_id: str, actor: Actor) -> Experiment:
        experiment = self._store.get_experiment(experiment_id)
        if experiment is None:
            raise _not_found("experiment", experiment_id)
        organization_service.require_access(actor, experiment.organization_id)
        return experiment

    def commit_version(
        self, experiment_id: str, payload: ExperimentVersionCreate, actor: Actor
    ) -> ExperimentVersion:
        """Create a new immutable version snapshot, advancing HEAD."""
        experiment = self.get_experiment(experiment_id, actor)
        parent_id = payload.parent_version_id or experiment.head_version_id
        if parent_id is not None:
            parent = self._store.get_version(parent_id)
            if parent is None or parent.experiment_id != experiment_id:
                raise _not_found("experiment_version", parent_id)

        # version_number is a placeholder: the store assigns it atomically and
        # advances HEAD in the same transaction, so concurrent commits to one
        # experiment cannot collide on a number or desync version_count.
        version = ExperimentVersion(
            experiment_id=experiment_id,
            organization_id=experiment.organization_id,
            version_number=0,
            parent_version_id=parent_id,
            message=payload.message,
            status=ExperimentStatus.DRAFT,
            blocks=payload.blocks,
            author_subject=actor.subject,
        )
        version = self._store.append_version(version)

        audit_service.record(
            organization_id=experiment.organization_id,
            actor=actor,
            event_type="eln.experiment_version_committed",
            resource_type="experiment_version",
            resource_id=version.id,
            payload={
                "experiment_id": experiment_id,
                "version_number": version.version_number,
                "parent_version_id": parent_id,
                "message": version.message,
            },
        )
        return version

    def list_versions(
        self, experiment_id: str, actor: Actor
    ) -> list[ExperimentVersion]:
        self.get_experiment(experiment_id, actor)
        return self._store.list_versions(experiment_id)

    def get_version(
        self, experiment_id: str, version_id: str, actor: Actor
    ) -> ExperimentVersion:
        self.get_experiment(experiment_id, actor)
        version = self._store.get_version(version_id)
        if version is None or version.experiment_id != experiment_id:
            raise _not_found("experiment_version", version_id)
        return version

    def update_version_status(
        self,
        experiment_id: str,
        version_id: str,
        payload: ExperimentStatusUpdate,
        actor: Actor,
    ) -> ExperimentVersion:
        """Transition a version's lifecycle status (draft -> in_review -> signed)."""
        version = self.get_version(experiment_id, version_id, actor)
        if version.status == ExperimentStatus.SIGNED:
            raise api_error(
                status_code=409,
                code="version_locked",
                message="Signed versions are immutable; commit a new version to amend",
                details={"version_id": version_id},
            )
        if (version.status, payload.status) not in _ALLOWED_STATUS_TRANSITIONS:
            raise api_error(
                status_code=400,
                code="invalid_transition",
                message="Experiment version status transition is not allowed",
                details={"from": version.status.value, "to": payload.status.value},
            )
        previous = version.status
        updated = version.model_copy(update={"status": payload.status})
        self._store.update_version(updated)
        audit_service.record(
            organization_id=version.organization_id,
            actor=actor,
            event_type="eln.experiment_version_status_changed",
            resource_type="experiment_version",
            resource_id=version_id,
            payload={
                "from": previous.value,
                "to": payload.status.value,
                "experiment_id": experiment_id,
            },
        )
        return updated

    # ----------------------------------------------------------------- #
    # Samples
    # ----------------------------------------------------------------- #
    def create_sample(self, payload: SampleCreate, actor: Actor) -> Sample:
        organization_service.require_access(actor, payload.organization_id)
        experiment = self._store.get_experiment(payload.experiment_id)
        if experiment is None or experiment.organization_id != payload.organization_id:
            raise _not_found("experiment", payload.experiment_id)

        well = self._normalize_well(payload.well_position)
        sample = Sample(**{**payload.model_dump(), "well_position": well})

        # The plate cap and well uniqueness are enforced inside the store, in the
        # same transaction as the insert. Checking here first would let concurrent
        # creates both pass and land a 97th sample on a 96-well plate.
        try:
            self._store.create_sample(sample, MAX_SAMPLES_PER_EXPERIMENT)
        except PlateFullError:
            raise api_error(
                status_code=409,
                code="plate_full",
                message=f"An experiment can hold at most {MAX_SAMPLES_PER_EXPERIMENT} samples (96-well plate)",
                details={
                    "experiment_id": payload.experiment_id,
                    "limit": MAX_SAMPLES_PER_EXPERIMENT,
                },
            ) from None
        except WellOccupiedError:
            raise api_error(
                status_code=409,
                code="well_occupied",
                message="Another sample already occupies this well",
                details={
                    "experiment_id": payload.experiment_id,
                    "well_position": well,
                },
            ) from None

        audit_service.record(
            organization_id=sample.organization_id,
            actor=actor,
            event_type="eln.sample_created",
            resource_type="sample",
            resource_id=sample.id,
            payload={
                "experiment_id": sample.experiment_id,
                "well_position": sample.well_position,
                "sample_type": sample.sample_type.value,
            },
        )
        return sample

    def list_samples(self, experiment_id: str, actor: Actor) -> list[Sample]:
        self.get_experiment(experiment_id, actor)
        return self._store.list_samples(experiment_id)

    def get_sample(self, sample_id: str, actor: Actor) -> Sample:
        sample = self._store.get_sample(sample_id)
        if sample is None:
            raise _not_found("sample", sample_id)
        organization_service.require_access(actor, sample.organization_id)
        return sample

    def update_sample(
        self, sample_id: str, payload: SampleUpdate, actor: Actor
    ) -> Sample:
        sample = self.get_sample(sample_id, actor)
        updates = payload.model_dump(exclude_unset=True)
        _reject_null_updates(updates, _SAMPLE_REQUIRED_FIELDS)
        if "well_position" in updates:
            updates["well_position"] = self._resolve_well(
                sample.experiment_id,
                updates["well_position"],
                exclude_sample_id=sample.id,
            )
        if not updates:
            return sample
        updated = sample.model_copy(update={**updates, "updated_at": _now()})
        self._store.update_sample(updated)
        audit_service.record(
            organization_id=updated.organization_id,
            actor=actor,
            event_type="eln.sample_updated",
            resource_type="sample",
            resource_id=updated.id,
            payload={"fields": sorted(updates.keys())},
        )
        return updated

    # ----------------------------------------------------------------- #
    # Datasets
    # ----------------------------------------------------------------- #
    def create_dataset(self, payload: DatasetCreate, actor: Actor) -> Dataset:
        organization_service.require_access(actor, payload.organization_id)
        sample = self._store.get_sample(payload.sample_id)
        if sample is None or sample.organization_id != payload.organization_id:
            raise _not_found("sample", payload.sample_id)
        dataset = Dataset(**payload.model_dump())
        self._store.create_dataset(dataset)
        audit_service.record(
            organization_id=dataset.organization_id,
            actor=actor,
            event_type="eln.dataset_created",
            resource_type="dataset",
            resource_id=dataset.id,
            payload={
                "sample_id": dataset.sample_id,
                "dataset_type": dataset.dataset_type.value,
            },
        )
        return dataset

    def list_datasets(self, sample_id: str, actor: Actor) -> list[Dataset]:
        self.get_sample(sample_id, actor)
        return self._store.list_datasets(sample_id)

    def get_dataset(self, dataset_id: str, actor: Actor) -> Dataset:
        dataset = self._store.get_dataset(dataset_id)
        if dataset is None:
            raise _not_found("dataset", dataset_id)
        organization_service.require_access(actor, dataset.organization_id)
        return dataset

    # ----------------------------------------------------------------- #
    # Helpers
    # ----------------------------------------------------------------- #
    def _visible_org_ids(self, actor: Actor, organization_id: str | None) -> list[str]:
        if organization_id is not None:
            organization_service.require_access(actor, organization_id)
            return [organization_id]
        return list(actor.organization_ids)

    def _normalize_well(self, well_position: str | None) -> str | None:
        """Validate a well coordinate. Occupancy is the store's job."""
        if well_position is None:
            return None
        normalized = normalize_well_position(well_position)
        if normalized is None:
            raise api_error(
                status_code=422,
                code="invalid_well",
                message="Well position must be within an 8x12 (96-well) plate, e.g. 'A1' to 'H12'",
                details={"well_position": well_position},
            )
        return normalized

    def _resolve_well(
        self,
        experiment_id: str,
        well_position: str | None,
        exclude_sample_id: str | None,
    ) -> str | None:
        normalized = self._normalize_well(well_position)
        if normalized is None:
            return None
        if self._store.well_occupied(
            experiment_id, normalized, exclude_sample_id=exclude_sample_id
        ):
            raise api_error(
                status_code=409,
                code="well_occupied",
                message="Another sample already occupies this well",
                details={"experiment_id": experiment_id, "well_position": normalized},
            )
        return normalized


# Update payloads type every field Optional so callers may omit them, but a subset
# maps to non-nullable columns. model_copy() skips validation, so an explicit JSON
# null would otherwise be written straight through into the stored record.
_PROJECT_REQUIRED_FIELDS = frozenset({"name", "status"})
_SAMPLE_REQUIRED_FIELDS = frozenset({"name", "sample_type", "status", "metadata"})


def _reject_null_updates(updates: dict[str, object], required: frozenset[str]) -> None:
    nulled = sorted(
        field for field in required if field in updates and updates[field] is None
    )
    if nulled:
        raise api_error(
            status_code=422,
            code="invalid_update",
            message="These fields cannot be set to null",
            details={"fields": nulled},
        )


def _not_found(resource: str, resource_id: str):
    return api_error(
        status_code=404,
        code="not_found",
        message=f"{resource.replace('_', ' ').capitalize()} not found",
        details={f"{resource}_id": resource_id},
    )


eln_service = ElnService()
# Backwards-compatible alias used by existing imports/tests during transition.
experiment_service = eln_service
