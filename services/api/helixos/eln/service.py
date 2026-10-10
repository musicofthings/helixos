"""Application service for the ELN hierarchy.

Coordinates workspaces, projects, experiments (with git-style versioning),
samples (96-well plate constrained), and datasets. Every mutation is tenant
scoped and recorded to the audit trail.
"""

from __future__ import annotations

import functools
import re
from datetime import datetime, timedelta, timezone
from typing import Literal

from helixos.audit.service import audit_service
from helixos.auth.schemas import Actor
from helixos.auth.service import DEMO_TOKENS, organization_service
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
    Protocol,
    ProtocolCreate,
    ProtocolImportRequest,
    ProtocolSourceProvider,
    ProtocolStatus,
    ProtocolStep,
    ProtocolUpdate,
    Sample,
    SampleCreate,
    SampleUpdate,
    Workspace,
    WorkspaceCategory,
    WorkspaceCreate,
    WorkspaceInvite,
    WorkspaceInviteCreate,
    WorkspaceShare,
    WorkspaceShareCreate,
    WorkspaceShareRole,
    WorkspaceShareUpdate,
    normalize_well_position,
)
from helixos.db.session import run_atomic
from helixos.eln.stores import (
    ElnStore,
    PageRequest,
    PageResult,
    InviteUnavailableError,
    PlateFullError,
    StaleStateError,
    WellOccupiedError,
)
from helixos.errors import api_error

WorkspaceAccess = Literal["owner", "editor", "viewer"]

_ACCESS_RANK: dict[WorkspaceAccess, int] = {
    "viewer": 1,
    "editor": 2,
    "owner": 3,
}
_KNOWN_SUBJECTS = {actor.subject for actor in DEMO_TOKENS.values()}
_EMAIL_SUBJECT = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _coerce_access(
    role: WorkspaceShareRole | Literal["owner"],
) -> WorkspaceAccess:
    if role == "owner":
        return "owner"
    return role.value

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


def _atomic(method):
    """Commit the wrapped mutation and its audit event in one transaction."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        return run_atomic(lambda: method(self, *args, **kwargs))

    return wrapper


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ElnService:
    """Coordinates the workspace -> project -> experiment -> sample -> dataset tree."""

    def __init__(self, store: ElnStore | None = None) -> None:
        self._store = store or build_eln_store()

    def use_store(self, store: ElnStore) -> None:
        """Replace the active store backend (used in tests)."""
        self._store = store

    def _audit(
        self,
        *,
        organization_id: str,
        actor: Actor,
        event_type: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        """Record an audit event for an actor already authorized by workspace policy.

        Workspace collaborators may belong to a different organization, so the
        org-membership check in ``audit_service.record`` would reject them after
        the write has already been persisted.
        """
        audit_service.record_system(
            organization_id=organization_id,
            actor_subject=actor.subject,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=payload,
        )

    # ----------------------------------------------------------------- #
    # Workspaces
    # ----------------------------------------------------------------- #
    @_atomic
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
        self._audit(
            organization_id=organization_id,
            actor=actor,
            event_type="eln.workspaces_seeded",
            resource_type="workspace",
            resource_id=organization_id,
            payload={"count": len(created)},
        )
        return created

    @_atomic
    def create_workspace(self, payload: WorkspaceCreate, actor: Actor) -> Workspace:
        organization_service.require_access(actor, payload.organization_id)
        workspace = Workspace(**payload.model_dump())
        self._store.create_workspace(workspace)
        self._audit(
            organization_id=workspace.organization_id,
            actor=actor,
            event_type="eln.workspace_created",
            resource_type="workspace",
            resource_id=workspace.id,
            payload={"name": workspace.name, "category": workspace.category.value},
        )
        return workspace

    def _shared_workspaces(
        self, actor: Actor, organization_id: str | None
    ) -> list[Workspace]:
        """Workspaces the actor reaches through a share (optionally within one org)."""
        shared: list[Workspace] = []
        for share in self._store.list_shares_for_subject(actor.subject):
            workspace = self._store.get_workspace(share.workspace_id)
            if workspace is None:
                continue
            if organization_id is not None and workspace.organization_id != organization_id:
                continue
            shared.append(workspace)
        return shared

    def _visibility(
        self, actor: Actor, organization_id: str | None
    ) -> tuple[list[str], list[str]]:
        """Resolve what the actor may list: (full-access org ids, shared workspace ids).

        Organization members see everything in their orgs; share grantees see only
        the shared workspaces. A caller with neither for the requested org is
        refused (403) rather than shown an empty list.
        """
        shared = self._shared_workspaces(actor, organization_id)
        if organization_id is not None:
            if organization_id in actor.organization_ids:
                return [organization_id], [w.id for w in shared]
            if not shared:
                organization_service.require_access(actor, organization_id)
            return [], [w.id for w in shared]
        return list(actor.organization_ids), [w.id for w in shared]

    def page_workspaces(
        self,
        actor: Actor,
        organization_id: str | None = None,
        page: PageRequest | None = None,
    ) -> PageResult[Workspace]:
        orgs, shared_ids = self._visibility(actor, organization_id)
        return self._store.page_workspaces(orgs, shared_ids, page)

    def list_workspaces(
        self, actor: Actor, organization_id: str | None = None
    ) -> list[Workspace]:
        return self.page_workspaces(actor, organization_id).items

    def get_workspace(self, workspace_id: str, actor: Actor) -> Workspace:
        return self.require_workspace_role(
            workspace_id, actor, WorkspaceShareRole.VIEWER
        )

    @_atomic
    def delete_workspace(self, workspace_id: str, actor: Actor) -> None:
        """Delete a workspace and everything nested beneath it."""
        workspace = self.require_workspace_role(workspace_id, actor, "owner")
        self._store.delete_workspace(workspace_id)
        self._audit(
            organization_id=workspace.organization_id,
            actor=actor,
            event_type="eln.workspace_deleted",
            resource_type="workspace",
            resource_id=workspace_id,
            payload={"name": workspace.name, "category": workspace.category.value},
        )

    # ----------------------------------------------------------------- #
    # Workspace collaboration
    # ----------------------------------------------------------------- #
    def list_collaboration(
        self, workspace_id: str, actor: Actor
    ) -> tuple[list[WorkspaceShare], list[WorkspaceInvite]]:
        self.require_workspace_role(workspace_id, actor, "owner")
        invites = [
            self._redact_invite_token(invite)
            for invite in self._store.list_invites(workspace_id)
        ]
        return self._store.list_shares(workspace_id), invites

    @_atomic
    def create_share(
        self, workspace_id: str, payload: WorkspaceShareCreate, actor: Actor
    ) -> WorkspaceShare:
        workspace = self.require_workspace_role(workspace_id, actor, "owner")
        subject = self._validate_share_subject(payload.subject)
        existing = self._store.find_share(workspace_id, subject)
        if existing is not None:
            raise api_error(
                status_code=409,
                code="share_exists",
                message="This subject already has a share on this workspace",
                details={"share_id": existing.id, "subject": existing.subject},
            )
        share = WorkspaceShare(
            workspace_id=workspace_id,
            organization_id=workspace.organization_id,
            subject=subject,
            role=payload.role,
            granted_by=actor.subject,
        )
        self._store.create_share(share)
        self._audit(
            organization_id=workspace.organization_id,
            actor=actor,
            event_type="eln.workspace_share_granted",
            resource_type="workspace_share",
            resource_id=share.id,
            payload={
                "workspace_id": workspace_id,
                "subject": share.subject,
                "role": share.role.value,
            },
        )
        return share

    @_atomic
    def update_share(
        self,
        workspace_id: str,
        share_id: str,
        payload: WorkspaceShareUpdate,
        actor: Actor,
    ) -> WorkspaceShare:
        workspace = self.require_workspace_role(workspace_id, actor, "owner")
        share = self._store.get_share(share_id)
        if share is None or share.workspace_id != workspace_id:
            raise _not_found("workspace_share", share_id)
        updated = share.model_copy(update={"role": payload.role})
        self._store.update_share(updated)
        self._audit(
            organization_id=workspace.organization_id,
            actor=actor,
            event_type="eln.workspace_share_updated",
            resource_type="workspace_share",
            resource_id=share_id,
            payload={
                "workspace_id": workspace_id,
                "subject": updated.subject,
                "role": updated.role.value,
            },
        )
        return updated

    @_atomic
    def revoke_share(self, workspace_id: str, share_id: str, actor: Actor) -> None:
        workspace = self.require_workspace_role(workspace_id, actor, "owner")
        share = self._store.get_share(share_id)
        if share is None or share.workspace_id != workspace_id:
            raise _not_found("workspace_share", share_id)
        self._store.delete_share(share_id)
        self._audit(
            organization_id=workspace.organization_id,
            actor=actor,
            event_type="eln.workspace_share_revoked",
            resource_type="workspace_share",
            resource_id=share_id,
            payload={"workspace_id": workspace_id, "subject": share.subject},
        )

    @_atomic
    def create_invite(
        self, workspace_id: str, payload: WorkspaceInviteCreate, actor: Actor
    ) -> WorkspaceInvite:
        workspace = self.require_workspace_role(workspace_id, actor, "owner")
        invite = WorkspaceInvite(
            workspace_id=workspace_id,
            organization_id=workspace.organization_id,
            role=payload.role,
            created_by=actor.subject,
            expires_at=_now() + timedelta(hours=payload.expires_in_hours),
            max_uses=payload.max_uses,
        )
        self._store.create_invite(invite)
        self._audit(
            organization_id=workspace.organization_id,
            actor=actor,
            event_type="eln.workspace_invite_created",
            resource_type="workspace_invite",
            resource_id=invite.id,
            payload={
                "workspace_id": workspace_id,
                "role": invite.role.value,
                "expires_at": invite.expires_at.isoformat(),
                "max_uses": invite.max_uses,
            },
        )
        return invite

    @_atomic
    def revoke_invite(self, workspace_id: str, invite_id: str, actor: Actor) -> None:
        workspace = self.require_workspace_role(workspace_id, actor, "owner")
        invite = self._store.get_invite(invite_id)
        if invite is None or invite.workspace_id != workspace_id:
            raise _not_found("workspace_invite", invite_id)
        if invite.revoked_at is not None:
            return
        updated = invite.model_copy(update={"revoked_at": _now()})
        self._store.update_invite(updated)
        self._audit(
            organization_id=workspace.organization_id,
            actor=actor,
            event_type="eln.workspace_invite_revoked",
            resource_type="workspace_invite",
            resource_id=invite_id,
            payload={"workspace_id": workspace_id},
        )

    def _accept_or_410(
        self, invite: WorkspaceInvite, share: WorkspaceShare | None
    ) -> None:
        try:
            self._store.accept_invite(invite, share)
        except InviteUnavailableError:
            raise api_error(
                status_code=410,
                code="invite_inactive",
                message="This invite has expired, been revoked, or reached its use limit",
                details={"invite_id": invite.id},
            ) from None

    @_atomic
    def accept_invite(self, token: str, actor: Actor) -> WorkspaceShare:
        invite = self._store.get_invite_by_token(token)
        if invite is None:
            raise _not_found("workspace_invite", token)
        if not invite.is_active:
            raise api_error(
                status_code=410,
                code="invite_inactive",
                message="This invite has expired, been revoked, or reached its use limit",
                details={"invite_id": invite.id},
            )
        existing = self._store.find_share(invite.workspace_id, actor.subject)
        if existing is not None:
            self._accept_or_410(invite, None)
            return existing

        share = WorkspaceShare(
            workspace_id=invite.workspace_id,
            organization_id=invite.organization_id,
            subject=actor.subject,
            role=invite.role,
            granted_by=invite.created_by,
        )
        self._accept_or_410(invite, share)
        # Acceptors may not yet belong to the workspace org; record without
        # an org-membership check so shared-with-me onboarding can succeed.
        audit_service.record_system(
            organization_id=invite.organization_id,
            actor_subject=actor.subject,
            event_type="eln.workspace_invite_accepted",
            resource_type="workspace_invite",
            resource_id=invite.id,
            payload={
                "workspace_id": invite.workspace_id,
                "share_id": share.id,
                "role": share.role.value,
            },
        )
        return share

    # ----------------------------------------------------------------- #
    # Projects
    # ----------------------------------------------------------------- #
    @_atomic
    def create_project(self, payload: ProjectCreate, actor: Actor) -> Project:
        workspace = self.require_workspace_role(
            payload.workspace_id, actor, WorkspaceShareRole.EDITOR
        )
        if workspace.organization_id != payload.organization_id:
            raise _not_found("workspace", payload.workspace_id)
        project = Project(**payload.model_dump())
        self._store.create_project(project)
        self._audit(
            organization_id=project.organization_id,
            actor=actor,
            event_type="eln.project_created",
            resource_type="project",
            resource_id=project.id,
            payload={"name": project.name, "workspace_id": project.workspace_id},
        )
        return project

    def page_projects(
        self,
        actor: Actor,
        organization_id: str | None = None,
        workspace_id: str | None = None,
        page: PageRequest | None = None,
    ) -> PageResult[Project]:
        if workspace_id is not None:
            workspace = self.require_workspace_role(
                workspace_id, actor, WorkspaceShareRole.VIEWER
            )
            return self._store.page_projects(
                [workspace.organization_id], workspace_id=workspace_id, page=page
            )
        orgs, shared_ids = self._visibility(actor, organization_id)
        return self._store.page_projects(orgs, shared_ids, page=page)

    def list_projects(
        self,
        actor: Actor,
        organization_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[Project]:
        return self.page_projects(actor, organization_id, workspace_id).items

    def get_project(self, project_id: str, actor: Actor) -> Project:
        project = self._store.get_project(project_id)
        if project is None:
            raise _not_found("project", project_id)
        self.require_workspace_role(
            project.workspace_id, actor, WorkspaceShareRole.VIEWER
        )
        return project

    @_atomic
    def update_project(
        self, project_id: str, payload: ProjectUpdate, actor: Actor
    ) -> Project:
        project = self._store.get_project(project_id)
        if project is None:
            raise _not_found("project", project_id)
        self.require_workspace_role(
            project.workspace_id, actor, WorkspaceShareRole.EDITOR
        )
        updates = payload.model_dump(exclude_unset=True)
        _reject_null_updates(updates, _PROJECT_REQUIRED_FIELDS)
        if not updates:
            return project
        updated = project.model_copy(update={**updates, "updated_at": _now()})
        self._store.update_project(updated)
        self._audit(
            organization_id=updated.organization_id,
            actor=actor,
            event_type="eln.project_updated",
            resource_type="project",
            resource_id=updated.id,
            payload={"fields": sorted(updates.keys())},
        )
        return updated

    @_atomic
    def delete_project(self, project_id: str, actor: Actor) -> None:
        """Delete a project and every experiment (and below) inside it."""
        project = self._store.get_project(project_id)
        if project is None:
            raise _not_found("project", project_id)
        self.require_workspace_role(
            project.workspace_id, actor, WorkspaceShareRole.EDITOR
        )
        self._store.delete_project(project_id)
        self._audit(
            organization_id=project.organization_id,
            actor=actor,
            event_type="eln.project_deleted",
            resource_type="project",
            resource_id=project_id,
            payload={"name": project.name, "workspace_id": project.workspace_id},
        )

    # ----------------------------------------------------------------- #
    # Protocols
    # ----------------------------------------------------------------- #
    @_atomic
    def create_protocol(self, payload: ProtocolCreate, actor: Actor) -> Protocol:
        workspace = self.require_workspace_role(
            payload.workspace_id, actor, WorkspaceShareRole.EDITOR
        )
        if workspace.organization_id != payload.organization_id:
            raise _not_found("workspace", payload.workspace_id)
        protocol = Protocol(**payload.model_dump())
        self._store.create_protocol(protocol)
        self._audit(
            organization_id=protocol.organization_id,
            actor=actor,
            event_type="eln.protocol_created",
            resource_type="protocol",
            resource_id=protocol.id,
            payload={"name": protocol.name, "workspace_id": protocol.workspace_id},
        )
        return protocol

    def page_protocols(
        self,
        actor: Actor,
        organization_id: str | None = None,
        workspace_id: str | None = None,
        page: PageRequest | None = None,
    ) -> PageResult[Protocol]:
        if workspace_id is not None:
            workspace = self.require_workspace_role(
                workspace_id, actor, WorkspaceShareRole.VIEWER
            )
            return self._store.page_protocols(
                [workspace.organization_id], workspace_id=workspace_id, page=page
            )
        orgs, shared_ids = self._visibility(actor, organization_id)
        return self._store.page_protocols(orgs, shared_ids, page=page)

    def list_protocols(
        self,
        actor: Actor,
        organization_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[Protocol]:
        return self.page_protocols(actor, organization_id, workspace_id).items

    def get_protocol(self, protocol_id: str, actor: Actor) -> Protocol:
        protocol = self._store.get_protocol(protocol_id)
        if protocol is None:
            raise _not_found("protocol", protocol_id)
        self.require_workspace_role(
            protocol.workspace_id, actor, WorkspaceShareRole.VIEWER
        )
        return protocol

    @_atomic
    def update_protocol(
        self, protocol_id: str, payload: ProtocolUpdate, actor: Actor
    ) -> Protocol:
        protocol = self._store.get_protocol(protocol_id)
        if protocol is None:
            raise _not_found("protocol", protocol_id)
        self.require_workspace_role(
            protocol.workspace_id, actor, WorkspaceShareRole.EDITOR
        )
        updates = payload.model_dump(exclude_unset=True)
        _reject_null_updates(updates, _PROTOCOL_REQUIRED_FIELDS)
        if not updates:
            return protocol
        updated = protocol.model_copy(update={**updates, "updated_at": _now()})
        try:
            self._store.update_protocol(updated)
        except KeyError as exc:
            raise _not_found("protocol", protocol_id) from exc
        self._audit(
            organization_id=updated.organization_id,
            actor=actor,
            event_type="eln.protocol_updated",
            resource_type="protocol",
            resource_id=updated.id,
            payload={"fields": sorted(updates.keys())},
        )
        return updated

    @_atomic
    def delete_protocol(self, protocol_id: str, actor: Actor) -> None:
        protocol = self._store.get_protocol(protocol_id)
        if protocol is None:
            raise _not_found("protocol", protocol_id)
        self.require_workspace_role(
            protocol.workspace_id, actor, WorkspaceShareRole.EDITOR
        )
        self._store.delete_protocol(protocol_id)
        self._audit(
            organization_id=protocol.organization_id,
            actor=actor,
            event_type="eln.protocol_deleted",
            resource_type="protocol",
            resource_id=protocol_id,
            payload={"name": protocol.name, "workspace_id": protocol.workspace_id},
        )

    @_atomic
    def import_protocol(self, payload: ProtocolImportRequest, actor: Actor) -> Protocol:
        """Create a draft protocol shell from an external source.

        Full remote fetch (protocols.io API, arbitrary URL scrape) is not wired
        yet — this persists source metadata and a placeholder step so the UI
        import flow works end-to-end.
        """
        if not payload.source_url and not payload.source_external_id:
            raise api_error(
                status_code=400,
                code="missing_import_locator",
                message="Provide source_url and/or source_external_id for import.",
            )

        name = payload.name
        if not name:
            if payload.source_external_id:
                name = f"Imported protocol {payload.source_external_id}"
            elif payload.source_url:
                name = f"Imported protocol from {payload.source_provider.value}"
            else:
                name = "Imported protocol"

        locator = payload.source_url or payload.source_external_id or ""
        draft = ProtocolCreate(
            organization_id=payload.organization_id,
            workspace_id=payload.workspace_id,
            name=name,
            description=(
                f"Stub import from {payload.source_provider.value}. "
                "Remote content fetch is not implemented yet — replace steps manually."
            ),
            steps=[
                ProtocolStep(
                    order=1,
                    title="Imported stub",
                    body=(
                        f"Source: {payload.source_provider.value}\n"
                        f"Locator: {locator}\n\n"
                        "Replace this step after reviewing the original protocol."
                    ),
                )
            ],
            source_provider=ProtocolSourceProvider(payload.source_provider.value),
            source_url=payload.source_url,
            source_external_id=payload.source_external_id,
        )
        protocol = self.create_protocol(draft, actor=actor)
        # create_protocol already audited as created; record import detail too.
        self._audit(
            organization_id=protocol.organization_id,
            actor=actor,
            event_type="eln.protocol_imported",
            resource_type="protocol",
            resource_id=protocol.id,
            payload={
                "source_provider": payload.source_provider.value,
                "source_url": payload.source_url,
                "source_external_id": payload.source_external_id,
            },
        )
        # Ensure status stays draft for stubs.
        if protocol.status != ProtocolStatus.DRAFT:
            return self.update_protocol(
                protocol.id, ProtocolUpdate(status=ProtocolStatus.DRAFT), actor=actor
            )
        return protocol

    # ----------------------------------------------------------------- #
    # Experiments + versions
    # ----------------------------------------------------------------- #
    @_atomic
    def create_experiment(self, payload: ExperimentCreate, actor: Actor) -> Experiment:
        """Create an experiment and its initial draft version (v1)."""
        if payload.project_id is not None:
            project = self._store.get_project(payload.project_id)
            if project is None or project.organization_id != payload.organization_id:
                raise _not_found("project", payload.project_id)
            self.require_workspace_role(
                project.workspace_id, actor, WorkspaceShareRole.EDITOR
            )
        else:
            # Legacy unscoped experiments: org membership required.
            organization_service.require_access(actor, payload.organization_id)

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

        self._audit(
            organization_id=experiment.organization_id,
            actor=actor,
            event_type="eln.experiment_created",
            resource_type="experiment",
            resource_id=experiment.id,
            payload={"name": experiment.name, "version_id": version.id},
        )
        return experiment

    def page_experiments(
        self,
        actor: Actor,
        organization_id: str | None = None,
        project_id: str | None = None,
        page: PageRequest | None = None,
    ) -> PageResult[Experiment]:
        if project_id is not None:
            project = self.get_project(project_id, actor)
            return self._store.page_experiments(
                [project.organization_id], project_id=project_id, page=page
            )
        orgs, shared_workspace_ids = self._visibility(actor, organization_id)
        shared_project_ids = (
            self._store.project_ids_in_workspaces(shared_workspace_ids)
            if shared_workspace_ids
            else []
        )
        return self._store.page_experiments(orgs, shared_project_ids, page=page)

    def list_experiments(
        self,
        actor: Actor,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> list[Experiment]:
        return self.page_experiments(actor, organization_id, project_id).items

    def get_experiment(self, experiment_id: str, actor: Actor) -> Experiment:
        experiment = self._store.get_experiment(experiment_id)
        if experiment is None:
            raise _not_found("experiment", experiment_id)
        self._require_experiment_role(
            experiment, actor, WorkspaceShareRole.VIEWER
        )
        return experiment

    @_atomic
    def delete_experiment(self, experiment_id: str, actor: Actor) -> None:
        """Delete an experiment and its versions, samples, and datasets."""
        experiment = self._store.get_experiment(experiment_id)
        if experiment is None:
            raise _not_found("experiment", experiment_id)
        self._require_experiment_role(
            experiment, actor, WorkspaceShareRole.EDITOR
        )
        self._store.delete_experiment(experiment_id)
        self._audit(
            organization_id=experiment.organization_id,
            actor=actor,
            event_type="eln.experiment_deleted",
            resource_type="experiment",
            resource_id=experiment_id,
            payload={"name": experiment.name, "project_id": experiment.project_id},
        )

    @_atomic
    def commit_version(
        self, experiment_id: str, payload: ExperimentVersionCreate, actor: Actor
    ) -> ExperimentVersion:
        """Create a new immutable version snapshot, advancing HEAD."""
        experiment = self._store.get_experiment(experiment_id)
        if experiment is None:
            raise _not_found("experiment", experiment_id)
        self._require_experiment_role(
            experiment, actor, WorkspaceShareRole.EDITOR
        )
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

        self._audit(
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

    def page_versions(
        self, experiment_id: str, actor: Actor, page: PageRequest | None = None
    ) -> PageResult[ExperimentVersion]:
        self.get_experiment(experiment_id, actor)
        return self._store.page_versions(experiment_id, page)

    def list_versions(
        self, experiment_id: str, actor: Actor
    ) -> list[ExperimentVersion]:
        return self.page_versions(experiment_id, actor).items

    def get_version(
        self, experiment_id: str, version_id: str, actor: Actor
    ) -> ExperimentVersion:
        self.get_experiment(experiment_id, actor)
        version = self._store.get_version(version_id)
        if version is None or version.experiment_id != experiment_id:
            raise _not_found("experiment_version", version_id)
        return version

    @_atomic
    def update_version_status(
        self,
        experiment_id: str,
        version_id: str,
        payload: ExperimentStatusUpdate,
        actor: Actor,
    ) -> ExperimentVersion:
        """Transition a version's lifecycle status (draft -> in_review -> signed)."""
        experiment = self._store.get_experiment(experiment_id)
        if experiment is None:
            raise _not_found("experiment", experiment_id)
        self._require_experiment_role(
            experiment, actor, WorkspaceShareRole.EDITOR
        )
        version = self._store.get_version(version_id)
        if version is None or version.experiment_id != experiment_id:
            raise _not_found("experiment_version", version_id)
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
        try:
            self._store.update_version(updated, expected_status=previous)
        except StaleStateError:
            raise api_error(
                status_code=409,
                code="version_state_changed",
                message="Version status changed concurrently; reload and retry",
                details={"version_id": version_id},
            ) from None
        self._audit(
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
    @_atomic
    def create_sample(self, payload: SampleCreate, actor: Actor) -> Sample:
        experiment = self._store.get_experiment(payload.experiment_id)
        if experiment is None or experiment.organization_id != payload.organization_id:
            raise _not_found("experiment", payload.experiment_id)
        self._require_experiment_role(
            experiment, actor, WorkspaceShareRole.EDITOR
        )

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

        self._audit(
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

    def page_samples(
        self, experiment_id: str, actor: Actor, page: PageRequest | None = None
    ) -> PageResult[Sample]:
        self.get_experiment(experiment_id, actor)
        return self._store.page_samples(experiment_id, page)

    def list_samples(self, experiment_id: str, actor: Actor) -> list[Sample]:
        return self.page_samples(experiment_id, actor).items

    def get_sample(self, sample_id: str, actor: Actor) -> Sample:
        sample = self._store.get_sample(sample_id)
        if sample is None:
            raise _not_found("sample", sample_id)
        experiment = self._store.get_experiment(sample.experiment_id)
        if experiment is None:
            raise _not_found("experiment", sample.experiment_id)
        self._require_experiment_role(
            experiment, actor, WorkspaceShareRole.VIEWER
        )
        return sample

    @_atomic
    def update_sample(
        self, sample_id: str, payload: SampleUpdate, actor: Actor
    ) -> Sample:
        sample = self._store.get_sample(sample_id)
        if sample is None:
            raise _not_found("sample", sample_id)
        experiment = self._store.get_experiment(sample.experiment_id)
        if experiment is None:
            raise _not_found("experiment", sample.experiment_id)
        self._require_experiment_role(
            experiment, actor, WorkspaceShareRole.EDITOR
        )
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
        self._audit(
            organization_id=updated.organization_id,
            actor=actor,
            event_type="eln.sample_updated",
            resource_type="sample",
            resource_id=updated.id,
            payload={"fields": sorted(updates.keys())},
        )
        return updated

    @_atomic
    def delete_sample(self, sample_id: str, actor: Actor) -> None:
        """Delete a sample and every dataset attached to it."""
        sample = self._store.get_sample(sample_id)
        if sample is None:
            raise _not_found("sample", sample_id)
        experiment = self._store.get_experiment(sample.experiment_id)
        if experiment is None:
            raise _not_found("experiment", sample.experiment_id)
        self._require_experiment_role(
            experiment, actor, WorkspaceShareRole.EDITOR
        )
        self._store.delete_sample(sample_id)
        self._audit(
            organization_id=sample.organization_id,
            actor=actor,
            event_type="eln.sample_deleted",
            resource_type="sample",
            resource_id=sample_id,
            payload={
                "experiment_id": sample.experiment_id,
                "name": sample.name,
                "well_position": sample.well_position,
            },
        )

    # ----------------------------------------------------------------- #
    # Datasets
    # ----------------------------------------------------------------- #
    @_atomic
    def create_dataset(self, payload: DatasetCreate, actor: Actor) -> Dataset:
        sample = self._store.get_sample(payload.sample_id)
        if sample is None or sample.organization_id != payload.organization_id:
            raise _not_found("sample", payload.sample_id)
        experiment = self._store.get_experiment(sample.experiment_id)
        if experiment is None:
            raise _not_found("experiment", sample.experiment_id)
        self._require_experiment_role(
            experiment, actor, WorkspaceShareRole.EDITOR
        )
        dataset = Dataset(**payload.model_dump())
        self._store.create_dataset(dataset)
        self._audit(
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

    def page_datasets(
        self, sample_id: str, actor: Actor, page: PageRequest | None = None
    ) -> PageResult[Dataset]:
        self.get_sample(sample_id, actor)
        return self._store.page_datasets(sample_id, page)

    def list_datasets(self, sample_id: str, actor: Actor) -> list[Dataset]:
        return self.page_datasets(sample_id, actor).items

    def get_dataset(self, dataset_id: str, actor: Actor) -> Dataset:
        dataset = self._store.get_dataset(dataset_id)
        if dataset is None:
            raise _not_found("dataset", dataset_id)
        sample = self._store.get_sample(dataset.sample_id)
        if sample is None:
            raise _not_found("sample", dataset.sample_id)
        experiment = self._store.get_experiment(sample.experiment_id)
        if experiment is None:
            raise _not_found("experiment", sample.experiment_id)
        self._require_experiment_role(
            experiment, actor, WorkspaceShareRole.VIEWER
        )
        return dataset

    # ----------------------------------------------------------------- #
    # Helpers
    # ----------------------------------------------------------------- #
    def require_workspace_role(
        self,
        workspace_id: str,
        actor: Actor,
        min_role: WorkspaceShareRole | Literal["owner"],
    ) -> Workspace:
        """Require at least ``min_role`` on a workspace (org members are owners)."""
        workspace = self._store.get_workspace(workspace_id)
        if workspace is None:
            raise _not_found("workspace", workspace_id)
        access = self._workspace_access_level(workspace, actor)
        needed = _coerce_access(min_role)
        if access is None or _ACCESS_RANK[access] < _ACCESS_RANK[needed]:
            raise api_error(
                status_code=403,
                code="forbidden",
                message="Caller does not have sufficient access to this workspace",
                details={
                    "workspace_id": workspace_id,
                    "required_role": needed,
                    "actual_role": access,
                },
            )
        return workspace

    def _workspace_access_level(
        self, workspace: Workspace, actor: Actor
    ) -> WorkspaceAccess | None:
        if workspace.organization_id in actor.organization_ids:
            return "owner"
        share = self._store.find_share(workspace.id, actor.subject)
        if share is None:
            return None
        return _coerce_access(share.role)

    def _require_experiment_role(
        self,
        experiment: Experiment,
        actor: Actor,
        min_role: WorkspaceShareRole | Literal["owner"],
    ) -> None:
        if experiment.project_id is not None:
            project = self._store.get_project(experiment.project_id)
            if project is None:
                raise _not_found("project", experiment.project_id)
            self.require_workspace_role(project.workspace_id, actor, min_role)
            return
        # Legacy experiments without a project: org membership only.
        organization_service.require_access(actor, experiment.organization_id)

    def _validate_share_subject(self, subject: str) -> str:
        cleaned = subject.strip()
        if cleaned in _KNOWN_SUBJECTS or _EMAIL_SUBJECT.match(cleaned):
            return cleaned
        raise api_error(
            status_code=422,
            code="invalid_subject",
            message="Share subject must be a known user id or an email address",
            details={"subject": cleaned},
        )

    @staticmethod
    def _redact_invite_token(invite: WorkspaceInvite) -> WorkspaceInvite:
        return invite.model_copy(update={"token": None})

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
_PROTOCOL_REQUIRED_FIELDS = frozenset({"name", "status"})
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
