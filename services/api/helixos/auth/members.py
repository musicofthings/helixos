"""Organization membership management (admin-only writes, audited)."""

from helixos.audit.service import audit_service
from helixos.auth.roles import MEMBERS_MANAGE, OrgRole
from helixos.auth.schemas import (
    Actor,
    MemberAddRequest,
    MemberAddResult,
    OrgMember,
    OrgMembers,
)
from helixos.auth.service import organization_service
from helixos.auth.store import AlreadyExists, LastAdmin, NotFound, auth_store
from helixos.db.session import run_atomic
from helixos.db.settings import get_database_settings
from helixos.errors import api_error

# Audit payloads carry ids and roles only: the log is append-only and hash-chained,
# so personal data (emails) must never be written into it.


def _translate(error: Exception):
    if isinstance(error, NotFound):
        return api_error(404, "not_found", str(error))
    if isinstance(error, AlreadyExists):
        return api_error(409, "member_exists", str(error))
    if isinstance(error, LastAdmin):
        return api_error(409, "last_admin", str(error))
    raise error


def _require_database() -> None:
    if not get_database_settings().is_configured:
        raise api_error(
            503,
            "members_unavailable",
            "Member management requires a configured database",
        )


class MemberService:
    def list(self, org_id: str, actor: Actor) -> OrgMembers:
        organization_service.require_access(actor, org_id)
        _require_database()
        return OrgMembers(
            members=auth_store.list_members(org_id),
            invites=auth_store.list_invites(org_id),
        )

    def add(
        self, org_id: str, request: MemberAddRequest, actor: Actor
    ) -> MemberAddResult:
        organization_service.require_permission(actor, org_id, MEMBERS_MANAGE)
        _require_database()

        def operation() -> MemberAddResult:
            member, invite = auth_store.add_member_by_email(
                org_id, request.email, request.role, invited_by=actor.subject
            )
            audit_service.record(
                organization_id=org_id,
                actor=actor,
                event_type="auth.member_added" if member else "auth.member_invited",
                resource_type="organization_member",
                resource_id=member.user_id if member else invite.id,
                payload={"role": request.role.value},
            )
            return MemberAddResult(member=member, invite=invite)

        try:
            return run_atomic(operation)
        except (NotFound, AlreadyExists, LastAdmin) as error:
            raise _translate(error) from None

    def set_role(
        self, org_id: str, user_id: str, role: OrgRole, actor: Actor
    ) -> OrgMember:
        organization_service.require_permission(actor, org_id, MEMBERS_MANAGE)
        _require_database()

        def operation() -> OrgMember:
            member = auth_store.set_role(org_id, user_id, role)
            audit_service.record(
                organization_id=org_id,
                actor=actor,
                event_type="auth.member_role_changed",
                resource_type="organization_member",
                resource_id=user_id,
                payload={"role": role.value},
            )
            return member

        try:
            return run_atomic(operation)
        except (NotFound, AlreadyExists, LastAdmin) as error:
            raise _translate(error) from None

    def remove(self, org_id: str, user_id: str, actor: Actor) -> None:
        organization_service.require_permission(actor, org_id, MEMBERS_MANAGE)
        _require_database()

        def operation() -> None:
            auth_store.remove_member(org_id, user_id)
            audit_service.record(
                organization_id=org_id,
                actor=actor,
                event_type="auth.member_removed",
                resource_type="organization_member",
                resource_id=user_id,
            )

        try:
            run_atomic(operation)
        except (NotFound, AlreadyExists, LastAdmin) as error:
            raise _translate(error) from None

    def revoke_invite(self, org_id: str, invite_id: str, actor: Actor) -> None:
        organization_service.require_permission(actor, org_id, MEMBERS_MANAGE)
        _require_database()

        def operation() -> None:
            auth_store.revoke_invite(org_id, invite_id)
            audit_service.record(
                organization_id=org_id,
                actor=actor,
                event_type="auth.member_invite_revoked",
                resource_type="organization_member",
                resource_id=invite_id,
            )

        try:
            run_atomic(operation)
        except (NotFound, AlreadyExists, LastAdmin) as error:
            raise _translate(error) from None


member_service = MemberService()
