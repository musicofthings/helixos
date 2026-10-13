"""SQL persistence for organizations, users and memberships.

Identity resolution and member management are only available with a configured
database; demo tokens never touch this store.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from helixos.auth.orm import MemberInviteORM, MembershipORM, OrganizationORM, UserORM
from helixos.auth.roles import OrgRole
from helixos.auth.schemas import Organization, OrgMember, OrgMemberInvite
from helixos.db.session import run_atomic, session_scope

# Skip the write that records activity unless the last one is older than this.
_TOUCH_AFTER = timedelta(minutes=5)


class AuthStoreError(Exception):
    """Base for expected, API-mappable store failures."""


class NotFound(AuthStoreError):
    pass


class AlreadyExists(AuthStoreError):
    pass


class LastAdmin(AuthStoreError):
    """The change would leave an organization without an admin."""


@dataclass(frozen=True)
class ResolvedIdentity:
    user_id: str
    email: str | None
    is_active: bool
    roles: dict[str, str] = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    # SQLite returns naive datetimes even for timezone-aware columns.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _org(row: OrganizationORM) -> Organization:
    return Organization(
        id=row.id,
        name=row.name,
        slug=row.slug,
        created_at=_aware(row.created_at),
        updated_at=_aware(row.updated_at),
    )


def _member(user: UserORM, membership: MembershipORM) -> OrgMember:
    return OrgMember(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=OrgRole(membership.role),
        joined_at=_aware(membership.created_at),
    )


def _invite(row: MemberInviteORM) -> OrgMemberInvite:
    return OrgMemberInvite(
        id=row.id,
        email=row.email,
        role=OrgRole(row.role),
        invited_by=row.invited_by,
        created_at=_aware(row.created_at),
    )


class AuthStore:
    # ------------------------------------------------------------------ #
    # Identity
    # ------------------------------------------------------------------ #
    def resolve_identity(
        self,
        *,
        issuer: str,
        subject: str,
        email: str | None,
        email_verified: bool,
        display_name: str | None,
    ) -> ResolvedIdentity:
        """Find or create the user for a verified token, claim any pending
        invites for its verified email, and return its memberships.

        Concurrent first sign-ins race on the (issuer, subject) unique key;
        ``run_atomic`` retries the loser, which then finds the winner's row.
        """
        trusted_email = email if (email and email_verified) else None

        def operation() -> ResolvedIdentity:
            now = _now()
            with session_scope() as session:
                user = session.scalar(
                    select(UserORM).where(
                        UserORM.issuer == issuer, UserORM.subject == subject
                    )
                )
                if user is None:
                    user = UserORM(
                        id=f"usr_{uuid4().hex}",
                        issuer=issuer,
                        subject=subject,
                        email=trusted_email,
                        display_name=display_name,
                        is_active=True,
                        created_at=now,
                        last_seen_at=now,
                    )
                    session.add(user)
                else:
                    if trusted_email and user.email != trusted_email:
                        user.email = trusted_email
                    if display_name and user.display_name != display_name:
                        user.display_name = display_name
                    if now - _aware(user.last_seen_at) > _TOUCH_AFTER:
                        user.last_seen_at = now
                session.flush()

                if trusted_email and user.is_active:
                    self._claim_invites(session, user, trusted_email, now)

                rows = session.scalars(
                    select(MembershipORM).where(MembershipORM.user_id == user.id)
                ).all()
                return ResolvedIdentity(
                    user_id=user.id,
                    email=user.email,
                    is_active=user.is_active,
                    roles={row.organization_id: row.role for row in rows},
                )

        return run_atomic(operation)

    @staticmethod
    def _claim_invites(session, user: UserORM, email: str, now: datetime) -> None:
        invites = session.scalars(
            select(MemberInviteORM).where(MemberInviteORM.email == email)
        ).all()
        for invite in invites:
            held = session.get(MembershipORM, (invite.organization_id, user.id))
            if held is None:
                session.add(
                    MembershipORM(
                        organization_id=invite.organization_id,
                        user_id=user.id,
                        role=invite.role,
                        created_at=now,
                    )
                )
            session.delete(invite)
        if invites:
            session.flush()

    # ------------------------------------------------------------------ #
    # Organizations
    # ------------------------------------------------------------------ #
    def create_organization(self, org_id: str, name: str, slug: str) -> Organization:
        now = _now()
        try:
            with session_scope() as session:
                row = OrganizationORM(
                    id=org_id, name=name, slug=slug, created_at=now, updated_at=now
                )
                session.add(row)
                session.flush()
                return _org(row)
        except IntegrityError:
            raise AlreadyExists(
                f"Organization id or slug already exists: {org_id}"
            ) from None

    def get_organization(self, org_id: str) -> Organization | None:
        with session_scope() as session:
            row = session.get(OrganizationORM, org_id)
            return _org(row) if row else None

    def list_organizations(
        self, org_ids: list[str] | None = None
    ) -> list[Organization]:
        with session_scope() as session:
            query = select(OrganizationORM).order_by(
                OrganizationORM.created_at, OrganizationORM.id
            )
            if org_ids is not None:
                query = query.where(OrganizationORM.id.in_(org_ids))
            return [_org(row) for row in session.scalars(query)]

    # ------------------------------------------------------------------ #
    # Members
    # ------------------------------------------------------------------ #
    def list_members(self, org_id: str) -> list[OrgMember]:
        with session_scope() as session:
            rows = session.execute(
                select(UserORM, MembershipORM)
                .join(MembershipORM, MembershipORM.user_id == UserORM.id)
                .where(MembershipORM.organization_id == org_id)
                .order_by(MembershipORM.created_at, UserORM.id)
            ).all()
            return [_member(user, membership) for user, membership in rows]

    def list_invites(self, org_id: str) -> list[OrgMemberInvite]:
        with session_scope() as session:
            rows = session.scalars(
                select(MemberInviteORM)
                .where(MemberInviteORM.organization_id == org_id)
                .order_by(MemberInviteORM.created_at, MemberInviteORM.id)
            )
            return [_invite(row) for row in rows]

    def add_member_by_email(
        self, org_id: str, email: str, role: OrgRole, invited_by: str
    ) -> tuple[OrgMember | None, OrgMemberInvite | None]:
        """Add the existing user with this verified email, else leave an invite
        that the first matching sign-in claims."""
        with session_scope() as session:
            self._lock_org(session, org_id)
            user = session.scalar(
                select(UserORM)
                .where(UserORM.email == email)
                .order_by(UserORM.created_at)
                .limit(1)
            )
            if user is not None:
                if session.get(MembershipORM, (org_id, user.id)) is not None:
                    raise AlreadyExists(f"{email} is already a member")
                membership = MembershipORM(
                    organization_id=org_id,
                    user_id=user.id,
                    role=role.value,
                    created_at=_now(),
                )
                session.add(membership)
                session.flush()
                return _member(user, membership), None

            invite = session.scalar(
                select(MemberInviteORM).where(
                    MemberInviteORM.organization_id == org_id,
                    MemberInviteORM.email == email,
                )
            )
            if invite is None:
                invite = MemberInviteORM(
                    id=f"minv_{uuid4().hex}",
                    organization_id=org_id,
                    email=email,
                    role=role.value,
                    invited_by=invited_by,
                    created_at=_now(),
                )
                session.add(invite)
            else:
                invite.role = role.value
                invite.invited_by = invited_by
            session.flush()
            return None, _invite(invite)

    def set_role(self, org_id: str, user_id: str, role: OrgRole) -> OrgMember:
        with session_scope() as session:
            self._lock_org(session, org_id)
            membership = session.get(MembershipORM, (org_id, user_id))
            if membership is None:
                raise NotFound(f"User {user_id} is not a member of {org_id}")
            if membership.role == OrgRole.ADMIN.value and role != OrgRole.ADMIN:
                self._require_other_admin(session, org_id, user_id)
            membership.role = role.value
            session.flush()
            return _member(session.get(UserORM, user_id), membership)

    def remove_member(self, org_id: str, user_id: str) -> None:
        with session_scope() as session:
            self._lock_org(session, org_id)
            membership = session.get(MembershipORM, (org_id, user_id))
            if membership is None:
                raise NotFound(f"User {user_id} is not a member of {org_id}")
            if membership.role == OrgRole.ADMIN.value:
                self._require_other_admin(session, org_id, user_id)
            session.delete(membership)

    def revoke_invite(self, org_id: str, invite_id: str) -> None:
        with session_scope() as session:
            invite = session.get(MemberInviteORM, invite_id)
            if invite is None or invite.organization_id != org_id:
                raise NotFound(f"Invite {invite_id} not found")
            session.delete(invite)

    def set_active(self, user_id: str, active: bool) -> None:
        with session_scope() as session:
            user = session.get(UserORM, user_id)
            if user is None:
                raise NotFound(f"User {user_id} not found")
            user.is_active = active

    # ------------------------------------------------------------------ #
    @staticmethod
    def _lock_org(session, org_id: str) -> None:
        """Serialize membership changes per organization (row lock on PostgreSQL)."""
        row = session.scalar(
            select(OrganizationORM)
            .where(OrganizationORM.id == org_id)
            .with_for_update()
        )
        if row is None:
            raise NotFound(f"Organization {org_id} not found")

    @staticmethod
    def _require_other_admin(session, org_id: str, excluding_user_id: str) -> None:
        others = session.scalar(
            select(func.count())
            .select_from(MembershipORM)
            .where(
                MembershipORM.organization_id == org_id,
                MembershipORM.role == OrgRole.ADMIN.value,
                MembershipORM.user_id != excluding_user_id,
            )
        )
        if not others:
            raise LastAdmin("An organization must keep at least one admin")


auth_store = AuthStore()
