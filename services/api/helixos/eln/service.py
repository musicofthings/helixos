"""Application service for ELN operations."""

from helixos.auth.schemas import Actor
from helixos.auth.service import organization_service
from helixos.eln.schemas import Experiment, ExperimentCreate


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
        return experiment

    def list_experiments(self, actor: Actor) -> list[Experiment]:
        """List experiments scoped to the authenticated actor."""
        experiments = list(self._experiments.values())
        visible = set(actor.organization_ids)
        return [experiment for experiment in experiments if experiment.organization_id in visible]


experiment_service = ExperimentService()
