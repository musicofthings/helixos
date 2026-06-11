"""ELN API routes."""

from fastapi import APIRouter, Depends

from helixos.auth.schemas import Actor
from helixos.auth.service import get_current_actor
from helixos.eln.schemas import Experiment, ExperimentCreate, ExperimentStatusUpdate
from helixos.eln.service import experiment_service

router = APIRouter(prefix="/experiments", tags=["eln"])


@router.post("", response_model=Experiment, status_code=201)
def create_experiment(payload: ExperimentCreate, actor: Actor = Depends(get_current_actor)) -> Experiment:
    """Create a draft experiment record."""
    return experiment_service.create_draft(payload, actor=actor)


@router.get("", response_model=list[Experiment])
def list_experiments(actor: Actor = Depends(get_current_actor)) -> list[Experiment]:
    """List experiment records visible to the caller."""
    return experiment_service.list_experiments(actor=actor)


@router.patch("/{experiment_id}", response_model=Experiment)
def update_experiment_status(
    experiment_id: str,
    payload: ExperimentStatusUpdate,
    actor: Actor = Depends(get_current_actor),
) -> Experiment:
    """Update experiment lifecycle status."""
    return experiment_service.update_status(experiment_id, payload, actor=actor)
