"""SQL-backed ELN store for Postgres and SQLite."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import TypeVar

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from helixos.db.session import in_unit_of_work, session_scope
from helixos.eln.orm import (
    DatasetORM,
    ExperimentORM,
    ExperimentVersionORM,
    ProjectORM,
    ProtocolORM,
    SampleORM,
    WorkspaceInviteORM,
    WorkspaceORM,
    WorkspaceShareORM,
)
from helixos.eln.schemas import (
    Dataset,
    Experiment,
    ExperimentBlock,
    ExperimentStatus,
    ExperimentVersion,
    Project,
    Protocol,
    ProtocolStep,
    Sample,
    Workspace,
    WorkspaceInvite,
    WorkspaceShare,
)
from helixos.eln.stores import (
    InviteUnavailableError,
    PlateFullError,
    StaleStateError,
    WellOccupiedError,
)


T = TypeVar("T")

# Concurrent version commits for one experiment can read the same max version
# number and collide on uq_eln_version_experiment_number; a busy SQLite writer
# surfaces as OperationalError. Both are transient — retry re-reads the max.
_MAX_ATTEMPTS = 12
_BACKOFF_BASE_SECONDS = 0.01
_BACKOFF_MAX_SECONDS = 0.25


def _retry_on_write_conflict(operation: Callable[[], T]) -> T:
    if in_unit_of_work():
        # A conflict poisons the shared transaction; the owner retries it whole.
        return operation()
    last_error: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return operation()
        except (IntegrityError, OperationalError) as exc:
            last_error = exc
            backoff = min(_BACKOFF_BASE_SECONDS * (2**attempt), _BACKOFF_MAX_SECONDS)
            time.sleep(random.uniform(0, backoff))
    raise RuntimeError(
        "Failed to commit experiment version after retries"
    ) from last_error


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _blocks_to_json(blocks: list[ExperimentBlock]) -> list[dict]:
    return [block.model_dump() for block in blocks]


def _blocks_from_json(raw: list | None) -> list[ExperimentBlock]:
    return [ExperimentBlock.model_validate(item) for item in (raw or [])]


class SqlElnStore:
    """Persist the ELN hierarchy in Postgres or SQLite."""

    # Workspaces
    def create_workspace(self, workspace: Workspace) -> Workspace:
        with session_scope() as session:
            session.add(
                WorkspaceORM(
                    id=workspace.id,
                    organization_id=workspace.organization_id,
                    name=workspace.name,
                    category=workspace.category.value,
                    subcategory=workspace.subcategory,
                    description=workspace.description,
                    is_default=workspace.is_default,
                    created_at=workspace.created_at,
                    updated_at=workspace.updated_at,
                )
            )
        return workspace

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        with session_scope() as session:
            row = session.get(WorkspaceORM, workspace_id)
            return _to_workspace(row) if row else None

    def list_workspaces(self, organization_ids: Sequence[str]) -> list[Workspace]:
        with session_scope() as session:
            rows = session.scalars(
                select(WorkspaceORM)
                .where(WorkspaceORM.organization_id.in_(list(organization_ids)))
                .order_by(WorkspaceORM.created_at.asc())
            ).all()
            return [_to_workspace(row) for row in rows]

    def count_workspaces(self, organization_id: str) -> int:
        with session_scope() as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(WorkspaceORM)
                    .where(WorkspaceORM.organization_id == organization_id)
                )
                or 0
            )

    def delete_workspace(self, workspace_id: str) -> None:
        # Cascade: datasets -> samples -> versions -> experiments -> projects ->
        # shares/invites -> workspace, in one transaction.
        with session_scope() as session:
            project_ids = list(
                session.scalars(
                    select(ProjectORM.id).where(
                        ProjectORM.workspace_id == workspace_id
                    )
                ).all()
            )
            for project_id in project_ids:
                self._delete_project_subtree(session, project_id)
            if project_ids:
                session.query(ProjectORM).filter(
                    ProjectORM.id.in_(project_ids)
                ).delete(synchronize_session=False)
            session.query(ProtocolORM).filter(
                ProtocolORM.workspace_id == workspace_id
            ).delete(synchronize_session=False)
            session.query(WorkspaceShareORM).filter(
                WorkspaceShareORM.workspace_id == workspace_id
            ).delete(synchronize_session=False)
            session.query(WorkspaceInviteORM).filter(
                WorkspaceInviteORM.workspace_id == workspace_id
            ).delete(synchronize_session=False)
            workspace = session.get(WorkspaceORM, workspace_id)
            if workspace is not None:
                session.delete(workspace)

    def create_share(self, share: WorkspaceShare) -> WorkspaceShare:
        with session_scope() as session:
            session.add(
                WorkspaceShareORM(
                    id=share.id,
                    workspace_id=share.workspace_id,
                    organization_id=share.organization_id,
                    subject=share.subject,
                    role=share.role.value,
                    granted_by=share.granted_by,
                    created_at=share.created_at,
                )
            )
        return share

    def get_share(self, share_id: str) -> WorkspaceShare | None:
        with session_scope() as session:
            row = session.get(WorkspaceShareORM, share_id)
            return _to_share(row) if row else None

    def list_shares(self, workspace_id: str) -> list[WorkspaceShare]:
        with session_scope() as session:
            rows = session.scalars(
                select(WorkspaceShareORM)
                .where(WorkspaceShareORM.workspace_id == workspace_id)
                .order_by(WorkspaceShareORM.created_at.asc())
            ).all()
            return [_to_share(row) for row in rows]

    def delete_share(self, share_id: str) -> None:
        with session_scope() as session:
            row = session.get(WorkspaceShareORM, share_id)
            if row is not None:
                session.delete(row)

    def find_share(self, workspace_id: str, subject: str) -> WorkspaceShare | None:
        with session_scope() as session:
            row = session.scalar(
                select(WorkspaceShareORM)
                .where(
                    WorkspaceShareORM.workspace_id == workspace_id,
                    WorkspaceShareORM.subject == subject,
                )
                .limit(1)
            )
            return _to_share(row) if row else None

    def list_shares_for_subject(self, subject: str) -> list[WorkspaceShare]:
        with session_scope() as session:
            rows = session.scalars(
                select(WorkspaceShareORM)
                .where(WorkspaceShareORM.subject == subject)
                .order_by(WorkspaceShareORM.created_at.asc())
            ).all()
            return [_to_share(row) for row in rows]

    def update_share(self, share: WorkspaceShare) -> WorkspaceShare:
        with session_scope() as session:
            row = session.get(WorkspaceShareORM, share.id)
            if row is None:
                raise KeyError(share.id)
            row.role = share.role.value
        return share

    def create_invite(self, invite: WorkspaceInvite) -> WorkspaceInvite:
        if not invite.token:
            raise ValueError("Invite token is required for persistence")
        with session_scope() as session:
            session.add(
                WorkspaceInviteORM(
                    id=invite.id,
                    workspace_id=invite.workspace_id,
                    organization_id=invite.organization_id,
                    token=invite.token,
                    role=invite.role.value,
                    created_by=invite.created_by,
                    expires_at=invite.expires_at,
                    revoked_at=invite.revoked_at,
                    accepted_count=invite.accepted_count,
                    max_uses=invite.max_uses,
                    created_at=invite.created_at,
                )
            )
        return invite

    def get_invite(self, invite_id: str) -> WorkspaceInvite | None:
        with session_scope() as session:
            row = session.get(WorkspaceInviteORM, invite_id)
            return _to_invite(row) if row else None

    def get_invite_by_token(self, token: str) -> WorkspaceInvite | None:
        with session_scope() as session:
            row = session.scalar(
                select(WorkspaceInviteORM)
                .where(WorkspaceInviteORM.token == token)
                .limit(1)
            )
            return _to_invite(row) if row else None

    def list_invites(self, workspace_id: str) -> list[WorkspaceInvite]:
        with session_scope() as session:
            rows = session.scalars(
                select(WorkspaceInviteORM)
                .where(WorkspaceInviteORM.workspace_id == workspace_id)
                .order_by(WorkspaceInviteORM.created_at.desc())
            ).all()
            return [_to_invite(row) for row in rows]

    def update_invite(self, invite: WorkspaceInvite) -> WorkspaceInvite:
        with session_scope() as session:
            row = session.get(WorkspaceInviteORM, invite.id)
            if row is not None:
                row.revoked_at = invite.revoked_at
                row.accepted_count = invite.accepted_count
                row.max_uses = invite.max_uses
        return invite

    def accept_invite(
        self, invite: WorkspaceInvite, share: WorkspaceShare | None
    ) -> tuple[WorkspaceInvite, WorkspaceShare | None]:
        # Optimistic loop: re-read, re-check activity, then bump the counter only
        # if it is unchanged. A lost race re-reads and re-checks the use limit.
        for _ in range(_MAX_ATTEMPTS):
            with session_scope() as session:
                # populate_existing: inside a shared unit of work the identity map
                # may hold a stale row; always re-read the committed state. The row
                # lock also serializes concurrent acceptors on PostgreSQL.
                row = session.get(
                    WorkspaceInviteORM,
                    invite.id,
                    populate_existing=True,
                    with_for_update=True,
                )
                if row is None:
                    raise KeyError(invite.id)
                current = _to_invite(row)
                if not current.is_active:
                    raise InviteUnavailableError(invite.id)
                result = session.execute(
                    update(WorkspaceInviteORM)
                    .where(
                        WorkspaceInviteORM.id == invite.id,
                        WorkspaceInviteORM.accepted_count == current.accepted_count,
                        WorkspaceInviteORM.revoked_at.is_(None),
                    )
                    .values(accepted_count=current.accepted_count + 1)
                )
                if result.rowcount == 1:
                    if share is not None:
                        session.add(
                            WorkspaceShareORM(
                                id=share.id,
                                workspace_id=share.workspace_id,
                                organization_id=share.organization_id,
                                subject=share.subject,
                                role=share.role.value,
                                granted_by=share.granted_by,
                                created_at=share.created_at,
                            )
                        )
                    return (
                        current.model_copy(
                            update={"accepted_count": current.accepted_count + 1}
                        ),
                        share,
                    )
        raise InviteUnavailableError(invite.id)

    # Projects
    def create_project(self, project: Project) -> Project:
        with session_scope() as session:
            session.add(
                ProjectORM(
                    id=project.id,
                    organization_id=project.organization_id,
                    workspace_id=project.workspace_id,
                    name=project.name,
                    description=project.description,
                    status=project.status.value,
                    created_at=project.created_at,
                    updated_at=project.updated_at,
                )
            )
        return project

    def get_project(self, project_id: str) -> Project | None:
        with session_scope() as session:
            row = session.get(ProjectORM, project_id)
            return _to_project(row) if row else None

    def list_projects(
        self, organization_ids: Sequence[str], workspace_id: str | None = None
    ) -> list[Project]:
        with session_scope() as session:
            query = select(ProjectORM).where(
                ProjectORM.organization_id.in_(list(organization_ids))
            )
            if workspace_id is not None:
                query = query.where(ProjectORM.workspace_id == workspace_id)
            rows = session.scalars(query.order_by(ProjectORM.created_at.asc())).all()
            return [_to_project(row) for row in rows]

    def update_project(self, project: Project) -> Project:
        with session_scope() as session:
            row = session.get(ProjectORM, project.id)
            if row is not None:
                row.name = project.name
                row.description = project.description
                row.status = project.status.value
                row.updated_at = project.updated_at
        return project

    def delete_project(self, project_id: str) -> None:
        with session_scope() as session:
            self._delete_project_subtree(session, project_id)
            project = session.get(ProjectORM, project_id)
            if project is not None:
                session.delete(project)

    def create_protocol(self, protocol: Protocol) -> Protocol:
        with session_scope() as session:
            session.add(
                ProtocolORM(
                    id=protocol.id,
                    organization_id=protocol.organization_id,
                    workspace_id=protocol.workspace_id,
                    name=protocol.name,
                    description=protocol.description,
                    status=protocol.status.value,
                    steps=[step.model_dump() for step in protocol.steps],
                    source_provider=protocol.source_provider.value,
                    source_url=protocol.source_url,
                    source_external_id=protocol.source_external_id,
                    created_at=protocol.created_at,
                    updated_at=protocol.updated_at,
                )
            )
        return protocol

    def get_protocol(self, protocol_id: str) -> Protocol | None:
        with session_scope() as session:
            row = session.get(ProtocolORM, protocol_id)
            return _to_protocol(row) if row else None

    def list_protocols(
        self, organization_ids: Sequence[str], workspace_id: str | None = None
    ) -> list[Protocol]:
        with session_scope() as session:
            query = select(ProtocolORM).where(
                ProtocolORM.organization_id.in_(list(organization_ids))
            )
            if workspace_id is not None:
                query = query.where(ProtocolORM.workspace_id == workspace_id)
            rows = session.scalars(query.order_by(ProtocolORM.created_at.asc())).all()
            return [_to_protocol(row) for row in rows]

    def update_protocol(self, protocol: Protocol) -> Protocol:
        with session_scope() as session:
            row = session.get(ProtocolORM, protocol.id)
            if row is None:
                raise KeyError(f"protocol:{protocol.id}")
            row.name = protocol.name
            row.description = protocol.description
            row.status = protocol.status.value
            row.steps = [step.model_dump() for step in protocol.steps]
            row.source_provider = protocol.source_provider.value
            row.source_url = protocol.source_url
            row.source_external_id = protocol.source_external_id
            row.updated_at = protocol.updated_at
        return protocol

    def delete_protocol(self, protocol_id: str) -> None:
        with session_scope() as session:
            row = session.get(ProtocolORM, protocol_id)
            if row is not None:
                session.delete(row)

    # Experiments
    def create_experiment_with_version(
        self, experiment: Experiment, version: ExperimentVersion
    ) -> Experiment:
        # One transaction, so an experiment can never be persisted without the
        # v1 its head_version_id points at.
        with session_scope() as session:
            session.add(
                ExperimentORM(
                    id=experiment.id,
                    organization_id=experiment.organization_id,
                    project_id=experiment.project_id,
                    name=experiment.name,
                    description=experiment.description,
                    head_version_id=experiment.head_version_id,
                    version_count=experiment.version_count,
                    created_at=experiment.created_at,
                    updated_at=experiment.updated_at,
                )
            )
            session.flush()
            session.add(_version_row(version))
        return experiment

    def get_experiment(self, experiment_id: str) -> Experiment | None:
        with session_scope() as session:
            row = session.get(ExperimentORM, experiment_id)
            return _to_experiment(row) if row else None

    def list_experiments(
        self, organization_ids: Sequence[str], project_id: str | None = None
    ) -> list[Experiment]:
        with session_scope() as session:
            query = select(ExperimentORM).where(
                ExperimentORM.organization_id.in_(list(organization_ids))
            )
            if project_id is not None:
                query = query.where(ExperimentORM.project_id == project_id)
            rows = session.scalars(query.order_by(ExperimentORM.created_at.asc())).all()
            return [_to_experiment(row) for row in rows]

    def update_experiment(self, experiment: Experiment) -> Experiment:
        with session_scope() as session:
            row = session.get(ExperimentORM, experiment.id)
            if row is not None:
                row.project_id = experiment.project_id
                row.name = experiment.name
                row.description = experiment.description
                row.head_version_id = experiment.head_version_id
                row.version_count = experiment.version_count
                row.updated_at = experiment.updated_at
        return experiment

    def delete_experiment(self, experiment_id: str) -> None:
        with session_scope() as session:
            self._delete_experiment_subtree(session, experiment_id)

    @staticmethod
    def _delete_project_subtree(session, project_id: str) -> None:
        experiment_ids = list(
            session.scalars(
                select(ExperimentORM.id).where(
                    ExperimentORM.project_id == project_id
                )
            ).all()
        )
        for experiment_id in experiment_ids:
            SqlElnStore._delete_experiment_subtree(session, experiment_id)

    @staticmethod
    def _delete_experiment_subtree(session, experiment_id: str) -> None:
        sample_ids = list(
            session.scalars(
                select(SampleORM.id).where(
                    SampleORM.experiment_id == experiment_id
                )
            ).all()
        )
        if sample_ids:
            session.query(DatasetORM).filter(
                DatasetORM.sample_id.in_(sample_ids)
            ).delete(synchronize_session=False)
        session.query(SampleORM).filter(
            SampleORM.experiment_id == experiment_id
        ).delete(synchronize_session=False)
        session.query(ExperimentVersionORM).filter(
            ExperimentVersionORM.experiment_id == experiment_id
        ).delete(synchronize_session=False)
        session.query(ExperimentORM).filter(
            ExperimentORM.id == experiment_id
        ).delete(synchronize_session=False)

    # Versions
    def append_version(self, version: ExperimentVersion) -> ExperimentVersion:
        def _insert() -> ExperimentVersion:
            with session_scope() as session:
                next_number = (
                    int(
                        session.scalar(
                            select(
                                func.coalesce(
                                    func.max(ExperimentVersionORM.version_number), 0
                                )
                            ).where(
                                ExperimentVersionORM.experiment_id
                                == version.experiment_id
                            )
                        )
                        or 0
                    )
                    + 1
                )
                stored = version.model_copy(update={"version_number": next_number})
                session.add(_version_row(stored))
                session.flush()

                experiment = session.get(ExperimentORM, stored.experiment_id)
                if experiment is not None:
                    experiment.head_version_id = stored.id
                    experiment.version_count = next_number
                    experiment.updated_at = _now()
                return stored

        # The unique constraint on (experiment_id, version_number) is what makes
        # the racing writer lose rather than duplicate; retry re-reads the max.
        return _retry_on_write_conflict(_insert)

    def get_version(self, version_id: str) -> ExperimentVersion | None:
        with session_scope() as session:
            row = session.get(ExperimentVersionORM, version_id)
            return _to_version(row) if row else None

    def list_versions(self, experiment_id: str) -> list[ExperimentVersion]:
        with session_scope() as session:
            rows = session.scalars(
                select(ExperimentVersionORM)
                .where(ExperimentVersionORM.experiment_id == experiment_id)
                .order_by(ExperimentVersionORM.version_number.asc())
            ).all()
            return [_to_version(row) for row in rows]

    def update_version(
        self, version: ExperimentVersion, expected_status: ExperimentStatus
    ) -> ExperimentVersion:
        with session_scope() as session:
            result = session.execute(
                update(ExperimentVersionORM)
                .where(
                    ExperimentVersionORM.id == version.id,
                    ExperimentVersionORM.status == expected_status.value,
                )
                .values(status=version.status.value)
            )
            if result.rowcount != 1:
                raise StaleStateError(version.id)
        return version

    # Samples
    def create_sample(self, sample: Sample, max_samples: int) -> Sample:
        def _insert() -> Sample:
            with session_scope() as session:
                # Serialize capacity allocation per plate: on PostgreSQL concurrent
                # transactions cannot see each other's uncommitted inserts, so the
                # post-insert count alone would let two writers both land sample 97.
                session.execute(
                    select(ExperimentORM.id)
                    .where(ExperimentORM.id == sample.experiment_id)
                    .with_for_update()
                ).first()
                if sample.well_position is not None:
                    taken = session.scalar(
                        select(SampleORM.id)
                        .where(
                            SampleORM.experiment_id == sample.experiment_id,
                            SampleORM.well_position == sample.well_position,
                        )
                        .limit(1)
                    )
                    if taken is not None:
                        raise WellOccupiedError

                session.add(
                    SampleORM(
                        id=sample.id,
                        organization_id=sample.organization_id,
                        experiment_id=sample.experiment_id,
                        name=sample.name,
                        sample_type=sample.sample_type.value,
                        well_position=sample.well_position,
                        status=sample.status.value,
                        sample_metadata=sample.metadata,
                        created_at=sample.created_at,
                        updated_at=sample.updated_at,
                    )
                )
                session.flush()

                # Count *after* the insert so our own row is included and any
                # concurrently-committed row is visible. Counting first would let
                # two writers both see 95 and land a 97th sample on the plate.
                # Over the cap means we lost the race: roll back and report it.
                total = int(
                    session.scalar(
                        select(func.count())
                        .select_from(SampleORM)
                        .where(SampleORM.experiment_id == sample.experiment_id)
                    )
                    or 0
                )
                if total > max_samples:
                    raise PlateFullError
                return sample

        # A racing writer that beat us to the well trips the unique constraint;
        # the retry re-reads and turns it into a clean WellOccupiedError.
        return _retry_on_write_conflict(_insert)

    def get_sample(self, sample_id: str) -> Sample | None:
        with session_scope() as session:
            row = session.get(SampleORM, sample_id)
            return _to_sample(row) if row else None

    def list_samples(self, experiment_id: str) -> list[Sample]:
        with session_scope() as session:
            rows = session.scalars(
                select(SampleORM)
                .where(SampleORM.experiment_id == experiment_id)
                .order_by(SampleORM.created_at.asc())
            ).all()
            return [_to_sample(row) for row in rows]

    def count_samples(self, experiment_id: str) -> int:
        with session_scope() as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(SampleORM)
                    .where(SampleORM.experiment_id == experiment_id)
                )
                or 0
            )

    def well_occupied(
        self,
        experiment_id: str,
        well_position: str,
        exclude_sample_id: str | None = None,
    ) -> bool:
        with session_scope() as session:
            query = select(SampleORM.id).where(
                SampleORM.experiment_id == experiment_id,
                SampleORM.well_position == well_position,
            )
            if exclude_sample_id is not None:
                query = query.where(SampleORM.id != exclude_sample_id)
            return session.scalar(query.limit(1)) is not None

    def update_sample(self, sample: Sample) -> Sample:
        with session_scope() as session:
            row = session.get(SampleORM, sample.id)
            if row is not None:
                row.name = sample.name
                row.sample_type = sample.sample_type.value
                row.well_position = sample.well_position
                row.status = sample.status.value
                row.sample_metadata = sample.metadata
                row.updated_at = sample.updated_at
        return sample

    def delete_sample(self, sample_id: str) -> None:
        with session_scope() as session:
            session.query(DatasetORM).filter(
                DatasetORM.sample_id == sample_id
            ).delete(synchronize_session=False)
            sample = session.get(SampleORM, sample_id)
            if sample is not None:
                session.delete(sample)

    # Datasets
    def create_dataset(self, dataset: Dataset) -> Dataset:
        with session_scope() as session:
            session.add(
                DatasetORM(
                    id=dataset.id,
                    organization_id=dataset.organization_id,
                    sample_id=dataset.sample_id,
                    name=dataset.name,
                    dataset_type=dataset.dataset_type.value,
                    sequence_id=dataset.sequence_id,
                    content=dataset.content,
                    created_at=dataset.created_at,
                    updated_at=dataset.updated_at,
                )
            )
        return dataset

    def get_dataset(self, dataset_id: str) -> Dataset | None:
        with session_scope() as session:
            row = session.get(DatasetORM, dataset_id)
            return _to_dataset(row) if row else None

    def list_datasets(self, sample_id: str) -> list[Dataset]:
        with session_scope() as session:
            rows = session.scalars(
                select(DatasetORM)
                .where(DatasetORM.sample_id == sample_id)
                .order_by(DatasetORM.created_at.asc())
            ).all()
            return [_to_dataset(row) for row in rows]


def _version_row(version: ExperimentVersion) -> ExperimentVersionORM:
    return ExperimentVersionORM(
        id=version.id,
        experiment_id=version.experiment_id,
        organization_id=version.organization_id,
        version_number=version.version_number,
        parent_version_id=version.parent_version_id,
        message=version.message,
        status=version.status.value,
        blocks=_blocks_to_json(version.blocks),
        author_subject=version.author_subject,
        created_at=version.created_at,
    )


def _to_workspace(row: WorkspaceORM) -> Workspace:
    return Workspace(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        category=row.category,
        subcategory=row.subcategory,
        description=row.description,
        is_default=row.is_default,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_share(row: WorkspaceShareORM) -> WorkspaceShare:
    return WorkspaceShare(
        id=row.id,
        workspace_id=row.workspace_id,
        organization_id=row.organization_id,
        subject=row.subject,
        role=row.role,
        granted_by=row.granted_by,
        created_at=row.created_at,
    )


def _ensure_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _to_invite(row: WorkspaceInviteORM) -> WorkspaceInvite:
    return WorkspaceInvite(
        id=row.id,
        workspace_id=row.workspace_id,
        organization_id=row.organization_id,
        token=row.token,
        role=row.role,
        created_by=row.created_by,
        expires_at=_ensure_aware(row.expires_at) or row.expires_at,
        revoked_at=_ensure_aware(row.revoked_at),
        accepted_count=row.accepted_count,
        max_uses=row.max_uses,
        created_at=_ensure_aware(row.created_at) or row.created_at,
    )


def _to_project(row: ProjectORM) -> Project:
    return Project(
        id=row.id,
        organization_id=row.organization_id,
        workspace_id=row.workspace_id,
        name=row.name,
        description=row.description,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_protocol(row: ProtocolORM) -> Protocol:
    return Protocol(
        id=row.id,
        organization_id=row.organization_id,
        workspace_id=row.workspace_id,
        name=row.name,
        description=row.description,
        status=row.status,
        steps=[ProtocolStep.model_validate(item) for item in (row.steps or [])],
        source_provider=row.source_provider,
        source_url=row.source_url,
        source_external_id=row.source_external_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_experiment(row: ExperimentORM) -> Experiment:
    return Experiment(
        id=row.id,
        organization_id=row.organization_id,
        project_id=row.project_id,
        name=row.name,
        description=row.description,
        head_version_id=row.head_version_id,
        version_count=row.version_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_version(row: ExperimentVersionORM) -> ExperimentVersion:
    return ExperimentVersion(
        id=row.id,
        experiment_id=row.experiment_id,
        organization_id=row.organization_id,
        version_number=row.version_number,
        parent_version_id=row.parent_version_id,
        message=row.message,
        status=row.status,
        blocks=_blocks_from_json(row.blocks),
        author_subject=row.author_subject,
        created_at=row.created_at,
    )


def _to_sample(row: SampleORM) -> Sample:
    return Sample(
        id=row.id,
        organization_id=row.organization_id,
        experiment_id=row.experiment_id,
        name=row.name,
        sample_type=row.sample_type,
        well_position=row.well_position,
        status=row.status,
        metadata=row.sample_metadata,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_dataset(row: DatasetORM) -> Dataset:
    return Dataset(
        id=row.id,
        organization_id=row.organization_id,
        sample_id=row.sample_id,
        name=row.name,
        dataset_type=row.dataset_type,
        sequence_id=row.sequence_id,
        content=row.content,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
