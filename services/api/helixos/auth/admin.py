"""Operator CLI for bootstrapping tenants.

    python -m helixos.auth.admin create-org --id org_acme --name "Acme Labs" \\
        --admin-email pi@acme.example
    python -m helixos.auth.admin add-member --org org_acme --email a@acme.example --role scientist
    python -m helixos.auth.admin list-orgs
    python -m helixos.auth.admin disable-user --user usr_...

Uses HELIX_DATABASE_URL (applies migrations first). Memberships are invites
until the person's first verified sign-in claims them.
"""

import argparse
import re
import sys

from helixos.audit.service import audit_service
from helixos.auth.roles import OrgRole
from helixos.auth.schemas import normalize_email
from helixos.auth.store import AlreadyExists, AuthStoreError, auth_store
from helixos.db.session import get_engine, init_db, run_atomic
from helixos.db.settings import get_database_settings

_ORG_ID = re.compile(r"^org_[a-z0-9][a-z0-9_]{1,40}$")
OPERATOR = "operator-cli"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:100] or "org"


def _audit(
    org_id: str, event_type: str, resource_type: str, resource_id: str, payload=None
) -> None:
    audit_service.record_system(
        organization_id=org_id,
        actor_subject=OPERATOR,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        payload=payload,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m helixos.auth.admin")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser(
        "create-org", help="create an organization and its first admin"
    )
    create.add_argument("--id", required=True, help="e.g. org_acme")
    create.add_argument("--name", required=True)
    create.add_argument("--slug")
    create.add_argument("--admin-email", required=True)

    add = commands.add_parser("add-member", help="add or invite a member")
    add.add_argument("--org", required=True)
    add.add_argument("--email", required=True)
    add.add_argument("--role", required=True, choices=[role.value for role in OrgRole])

    commands.add_parser("list-orgs", help="list organizations")

    disable = commands.add_parser("disable-user", help="block a user from signing in")
    disable.add_argument("--user", required=True)
    enable = commands.add_parser("enable-user", help="re-enable a blocked user")
    enable.add_argument("--user", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    settings = get_database_settings()
    if not settings.is_configured or get_engine(settings) is None:
        print("HELIX_DATABASE_URL is not configured", file=sys.stderr)
        return 1
    init_db(settings)

    try:
        if args.command == "create-org":
            if not _ORG_ID.match(args.id):
                print(
                    "--id must look like org_acme (lowercase letters, digits, _)",
                    file=sys.stderr,
                )
                return 2
            email = normalize_email(args.admin_email)

            def create():
                created = auth_store.create_organization(
                    args.id, args.name.strip(), args.slug or _slug(args.name)
                )
                auth_store.add_member_by_email(
                    created.id, email, OrgRole.ADMIN, invited_by=OPERATOR
                )
                _audit(
                    created.id, "auth.organization_created", "organization", created.id
                )
                return created

            org = run_atomic(create)
            print(
                f"Created {org.id} ({org.name}); {email} becomes admin on first sign-in"
            )
        elif args.command == "add-member":

            def add():
                result = auth_store.add_member_by_email(
                    args.org,
                    normalize_email(args.email),
                    OrgRole(args.role),
                    invited_by=OPERATOR,
                )
                _audit(
                    args.org,
                    "auth.member_added" if result[0] else "auth.member_invited",
                    "organization_member",
                    result[0].user_id if result[0] else result[1].id,
                    {"role": args.role},
                )
                return result

            member, invite = run_atomic(add)
            print(
                "Added existing user" if member else "Invited; claimed on first sign-in"
            )
        elif args.command == "list-orgs":
            for org in auth_store.list_organizations():
                print(f"{org.id}\t{org.slug}\t{org.name}")
        elif args.command == "disable-user":
            auth_store.set_active(args.user, False)
            print(f"Disabled {args.user}")
        elif args.command == "enable-user":
            auth_store.set_active(args.user, True)
            print(f"Enabled {args.user}")
    except AlreadyExists as error:
        print(f"Already exists: {error}", file=sys.stderr)
        return 3
    except AuthStoreError as error:
        print(str(error), file=sys.stderr)
        return 3
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
