"""ELN API routes for the workspace -> project -> experiment -> sample -> dataset tree."""

from fastapi import APIRouter, Depends, Query

from helixos.auth.schemas import Actor
from helixos.auth.service import get_current_actor
from helixos.eln.schemas import (
    Dataset,
    DatasetCreate,
    Experiment,
    ExperimentCreate,
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
    WorkspaceCreate,
)
from helixos.eln.service import eln_service
from pydantic import BaseModel

router = APIRouter(tags=["eln"])


class SeedWorkspacesRequest(BaseModel):
    """Payload for seeding the default workspace set."""

    organization_id: str


# --------------------------------------------------------------------------- #
# Workspaces
# --------------------------------------------------------------------------- #
@router.post("/workspaces", response_model=Workspace, status_code=201)
def create_workspace(
    payload: WorkspaceCreate, actor: Actor = Depends(get_current_actor)
) -> Workspace:
    """Create a workspace (a scientific category container)."""
    return eln_service.create_workspace(payload, actor=actor)


@router.get("/workspaces", response_model=list[Workspace])
def list_workspaces(
    organization_id: str | None = Query(default=None),
    actor: Actor = Depends(get_current_actor),
) -> list[Workspace]:
    """List workspaces visible to the caller."""
    return eln_service.list_workspaces(actor=actor, organization_id=organization_id)


@router.post("/workspaces/seed-defaults", response_model=list[Workspace])
def seed_default_workspaces(
    payload: SeedWorkspacesRequest, actor: Actor = Depends(get_current_actor)
) -> list[Workspace]:
    """Seed the default workspace set for an organization (idempotent)."""
    return eln_service.ensure_default_workspaces(payload.organization_id, actor=actor)


@router.get("/workspaces/{workspace_id}", response_model=Workspace)
def get_workspace(
    workspace_id: str, actor: Actor = Depends(get_current_actor)
) -> Workspace:
    """Fetch a workspace by id."""
    return eln_service.get_workspace(workspace_id, actor=actor)


# --------------------------------------------------------------------------- #
# Projects
# --------------------------------------------------------------------------- #
@router.post("/projects", response_model=Project, status_code=201)
def create_project(
    payload: ProjectCreate, actor: Actor = Depends(get_current_actor)
) -> Project:
    """Create a project within a workspace."""
    return eln_service.create_project(payload, actor=actor)


@router.get("/projects", response_model=list[Project])
def list_projects(
    organization_id: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
    actor: Actor = Depends(get_current_actor),
) -> list[Project]:
    """List projects, optionally filtered by workspace."""
    return eln_service.list_projects(
        actor=actor, organization_id=organization_id, workspace_id=workspace_id
    )


@router.get("/projects/{project_id}", response_model=Project)
def get_project(project_id: str, actor: Actor = Depends(get_current_actor)) -> Project:
    """Fetch a project by id."""
    return eln_service.get_project(project_id, actor=actor)


@router.patch("/projects/{project_id}", response_model=Project)
def update_project(
    project_id: str, payload: ProjectUpdate, actor: Actor = Depends(get_current_actor)
) -> Project:
    """Update a project's mutable fields."""
    return eln_service.update_project(project_id, payload, actor=actor)


# --------------------------------------------------------------------------- #
# Experiments + versions
# --------------------------------------------------------------------------- #
@router.post("/experiments", response_model=Experiment, status_code=201)
def create_experiment(
    payload: ExperimentCreate, actor: Actor = Depends(get_current_actor)
) -> Experiment:
    """Create an experiment and its initial draft version."""
    return eln_service.create_experiment(payload, actor=actor)


@router.get("/experiments", response_model=list[Experiment])
def list_experiments(
    organization_id: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    actor: Actor = Depends(get_current_actor),
) -> list[Experiment]:
    """List experiments visible to the caller."""
    return eln_service.list_experiments(
        actor=actor, organization_id=organization_id, project_id=project_id
    )


@router.get("/experiments/{experiment_id}", response_model=Experiment)
def get_experiment(
    experiment_id: str, actor: Actor = Depends(get_current_actor)
) -> Experiment:
    """Fetch an experiment by id."""
    return eln_service.get_experiment(experiment_id, actor=actor)


@router.post(
    "/experiments/{experiment_id}/versions",
    response_model=ExperimentVersion,
    status_code=201,
)
def commit_experiment_version(
    experiment_id: str,
    payload: ExperimentVersionCreate,
    actor: Actor = Depends(get_current_actor),
) -> ExperimentVersion:
    """Commit a new immutable version snapshot and advance HEAD."""
    return eln_service.commit_version(experiment_id, payload, actor=actor)


@router.get(
    "/experiments/{experiment_id}/versions", response_model=list[ExperimentVersion]
)
def list_experiment_versions(
    experiment_id: str, actor: Actor = Depends(get_current_actor)
) -> list[ExperimentVersion]:
    """List the version history for an experiment."""
    return eln_service.list_versions(experiment_id, actor=actor)


@router.get(
    "/experiments/{experiment_id}/versions/{version_id}",
    response_model=ExperimentVersion,
)
def get_experiment_version(
    experiment_id: str, version_id: str, actor: Actor = Depends(get_current_actor)
) -> ExperimentVersion:
    """Fetch a single experiment version."""
    return eln_service.get_version(experiment_id, version_id, actor=actor)


@router.patch(
    "/experiments/{experiment_id}/versions/{version_id}",
    response_model=ExperimentVersion,
)
def update_experiment_version_status(
    experiment_id: str,
    version_id: str,
    payload: ExperimentStatusUpdate,
    actor: Actor = Depends(get_current_actor),
) -> ExperimentVersion:
    """Transition an experiment version's lifecycle status."""
    return eln_service.update_version_status(
        experiment_id, version_id, payload, actor=actor
    )


# --------------------------------------------------------------------------- #
# Samples
# --------------------------------------------------------------------------- #
@router.post("/samples", response_model=Sample, status_code=201)
def create_sample(
    payload: SampleCreate, actor: Actor = Depends(get_current_actor)
) -> Sample:
    """Create a sample under an experiment (max 96 per experiment)."""
    return eln_service.create_sample(payload, actor=actor)


@router.get("/experiments/{experiment_id}/samples", response_model=list[Sample])
def list_samples(
    experiment_id: str, actor: Actor = Depends(get_current_actor)
) -> list[Sample]:
    """List samples for an experiment."""
    return eln_service.list_samples(experiment_id, actor=actor)


@router.get("/samples/{sample_id}", response_model=Sample)
def get_sample(sample_id: str, actor: Actor = Depends(get_current_actor)) -> Sample:
    """Fetch a sample by id."""
    return eln_service.get_sample(sample_id, actor=actor)


@router.patch("/samples/{sample_id}", response_model=Sample)
def update_sample(
    sample_id: str, payload: SampleUpdate, actor: Actor = Depends(get_current_actor)
) -> Sample:
    """Update a sample's mutable fields."""
    return eln_service.update_sample(sample_id, payload, actor=actor)


# --------------------------------------------------------------------------- #
# Datasets
# --------------------------------------------------------------------------- #
@router.post("/datasets", response_model=Dataset, status_code=201)
def create_dataset(
    payload: DatasetCreate, actor: Actor = Depends(get_current_actor)
) -> Dataset:
    """Attach a dataset to a sample."""
    return eln_service.create_dataset(payload, actor=actor)


@router.get("/samples/{sample_id}/datasets", response_model=list[Dataset])
def list_datasets(
    sample_id: str, actor: Actor = Depends(get_current_actor)
) -> list[Dataset]:
    """List datasets attached to a sample."""
    return eln_service.list_datasets(sample_id, actor=actor)


@router.get("/datasets/{dataset_id}", response_model=Dataset)
def get_dataset(dataset_id: str, actor: Actor = Depends(get_current_actor)) -> Dataset:
    """Fetch a dataset by id."""
    return eln_service.get_dataset(dataset_id, actor=actor)
