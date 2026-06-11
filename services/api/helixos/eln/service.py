"""Application service for ELN operations."""

from datetime import datetime, timezone

from helixos.audit.service import audit_service
from helixos.auth.schemas import Actor
from helixos.auth.service import organization_service
from helixos.eln.schemas import Experiment, ExperimentCreate, ExperimentStatus, ExperimentStatusUpdate
from helixos.errors import api_error

_ALLOWED_STATUS_TRANSITIONS: frozenset[tuple[ExperimentStatus, ExperimentStatus]] = frozenset(
    {
        (ExperimentStatus.DRAFT, ExperimentStatus.IN_REVIEW),
        (ExperimentStatus.IN_REVIEW, ExperimentStatus.SIGNED),
    }
)


class ExperimentService:
    """Coordinates experiment use cases.

    The starter kit uses in-memory storage so the API is runnable before the
    database layer is introduced. Replace this with SQLAlchemy repositories
    when persistence is added.
    """

    def __init__(self) -> None:
        self._experiments: dict[str, Experiment] = {}

    def create_draft(self, payload: ExperimentCreate, actor: Actor) -> Experiment:
        """Create an experiment draft."""
        organization_service.require_access(actor, payload.organization_id)
        experiment = Experiment(**payload.model_dump())
        self._experiments[experiment.id] = experiment
        audit_service.record(
            organization_id=experiment.organization_id,
            actor=actor,
            event_type="eln.experiment_created",
            resource_type="experiment",
            resource_id=experiment.id,
            payload={"title": experiment.title, "status": experiment.status.value},
        )
        return experiment

    def list_experiments(self, actor: Actor) -> list[Experiment]:
        """List experiments scoped to the authenticated actor."""
        experiments = list(self._experiments.values())
        visible = set(actor.organization_ids)
        return [experiment for experiment in experiments if experiment.organization_id in visible]

    def update_status(self, experiment_id: str, payload: ExperimentStatusUpdate, actor: Actor) -> Experiment:
        """Transition an experiment to a new lifecycle status."""
        experiment = self._experiments.get(experiment_id)
        if experiment is None:
            raise api_error(
                status_code=404,
                code="not_found",
                message="Experiment not found",
                details={"experiment_id": experiment_id},
            )

        organization_service.require_access(actor, experiment.organization_id)
        if (experiment.status, payload.status) not in _ALLOWED_STATUS_TRANSITIONS:
            raise api_error(
                status_code=400,
                code="invalid_transition",
                message="Experiment status transition is not allowed",
                details={"from": experiment.status.value, "to": payload.status.value},
            )

        previous_status = experiment.status
        updated = experiment.model_copy(
            update={
                "status": payload.status,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._experiments[experiment_id] = updated
        audit_service.record(
            organization_id=updated.organization_id,
            actor=actor,
            event_type="eln.experiment_status_changed",
            resource_type="experiment",
            resource_id=updated.id,
            payload={
                "from": previous_status.value,
                "to": payload.status.value,
                "title": updated.title,
            },
        )
        return updated


experiment_service = ExperimentService()
