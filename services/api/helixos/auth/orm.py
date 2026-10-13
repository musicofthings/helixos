"""SQLAlchemy ORM models for organizations, users and memberships."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from helixos.db.base import Base


class OrganizationORM(Base):
    __tablename__ = "auth_organizations"
    __table_args__ = (UniqueConstraint("slug", name="uq_auth_organization_slug"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class UserORM(Base):
    """A person, identified by the identity provider's issuer + subject."""

    __tablename__ = "auth_users"
    __table_args__ = (
        UniqueConstraint("issuer", "subject", name="uq_auth_user_identity"),
        Index("ix_auth_users_email", "email"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class MembershipORM(Base):
    __tablename__ = "auth_memberships"
    __table_args__ = (Index("ix_auth_memberships_user", "user_id"),)

    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("auth_organizations.id"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("auth_users.id"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class MemberInviteORM(Base):
    """Pre-provisioned membership, claimed by the first verified sign-in with that email."""

    __tablename__ = "auth_member_invites"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "email", name="uq_auth_member_invite_email"
        ),
        Index("ix_auth_member_invites_email", "email"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("auth_organizations.id"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    invited_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
