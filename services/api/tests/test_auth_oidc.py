"""End to end: OIDC sign-in, tenant bootstrap, membership and role enforcement."""

import json

import pytest
from fastapi.testclient import TestClient
from oidc_support import AUDIENCE, ISSUER, FakeIdp

from helixos.auth import admin
from helixos.auth.roles import OrgRole
from helixos.auth.store import auth_store
from helixos.db.session import reset_engine
from helixos.main import create_app

ORG = "org_acme"
ADMIN = ("idp|admin", "admin@acme.test")


@pytest.fixture
def idp(monkeypatch) -> FakeIdp:
    fake = FakeIdp()
    monkeypatch.setattr("helixos.auth.oidc.http_get_json", fake.fetch)
    return fake


@pytest.fixture
def client(tmp_path, monkeypatch, idp) -> TestClient:
    monkeypatch.setenv("HELIX_ENV", "staging")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example.test")
    monkeypatch.setenv("HELIX_DATABASE_URL", f"sqlite:///{tmp_path / 'auth.db'}")
    monkeypatch.setenv("HELIX_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("HELIX_OIDC_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("HELIX_OIDC_JWKS_URL", "https://idp.example.test/jwks.json")
    monkeypatch.setattr("helixos.auth.service._verifier", None)
    reset_engine()
    try:
        yield TestClient(create_app())
    finally:
        reset_engine()


def bearer(idp: FakeIdp, sub: str, email: str | None, **kwargs) -> dict[str, str]:
    return {"Authorization": f"Bearer {idp.token(sub, email=email, **kwargs)}"}


@pytest.fixture
def acme(client, idp) -> dict[str, str]:
    """Bootstrap the org via the operator CLI; return the admin's headers."""
    code = admin.main(
        ["create-org", "--id", ORG, "--name", "Acme Labs", "--admin-email", ADMIN[1]]
    )
    assert code == 0
    headers = bearer(idp, *ADMIN)
    assert client.get("/api/v1/organizations", headers=headers).status_code == 200
    return headers


def join(
    client, idp, sub: str, email: str, role: str, *, verified: bool = True
) -> dict[str, str]:
    """Pre-provision a member by email, then sign in so the invite is claimed."""
    auth_store.add_member_by_email(ORG, email, OrgRole(role), invited_by="test")
    headers = bearer(idp, sub, email, email_verified=verified)
    assert client.get("/api/v1/organizations", headers=headers).status_code == 200
    return headers


def member_id(client, headers, email: str) -> str:
    members = client.get(
        f"/api/v1/organizations/{ORG}/members", headers=headers
    ).json()["members"]
    return next(m["user_id"] for m in members if m["email"] == email)


# --------------------------------------------------------------------------- #
# Sign-in
# --------------------------------------------------------------------------- #
def test_first_sign_in_creates_a_user_with_no_organizations(client, idp) -> None:
    response = client.get(
        "/api/v1/organizations", headers=bearer(idp, "idp|new", "new@x.test")
    )
    assert response.status_code == 200
    assert response.json() == []


def test_missing_invalid_and_demo_tokens_are_rejected(client, idp) -> None:
    assert client.get("/api/v1/organizations").status_code == 401
    assert (
        client.get(
            "/api/v1/organizations", headers={"Authorization": "Bearer junk"}
        ).status_code
        == 401
    )
    demo = {"Authorization": "Bearer org-demo-token"}
    assert client.get("/api/v1/organizations", headers=demo).status_code == 401
    tampered = idp.token() + "x"
    assert (
        client.get(
            "/api/v1/organizations", headers={"Authorization": f"Bearer {tampered}"}
        ).status_code
        == 401
    )


def test_identity_provider_outage_is_503_not_401(client, idp) -> None:
    idp.down = True
    response = client.get("/api/v1/organizations", headers=bearer(idp, *ADMIN))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "auth_unavailable"


def test_operator_bootstrap_makes_the_first_verified_sign_in_an_admin(
    client, idp, acme
) -> None:
    orgs = client.get("/api/v1/organizations", headers=acme).json()
    assert [o["id"] for o in orgs] == [ORG]

    members = client.get(f"/api/v1/organizations/{ORG}/members", headers=acme).json()
    assert [(m["email"], m["role"]) for m in members["members"]] == [
        (ADMIN[1], "admin")
    ]
    assert members["invites"] == []


def test_an_unverified_email_cannot_claim_an_invite(client, idp, acme) -> None:
    auth_store.add_member_by_email(
        ORG, "victim@acme.test", OrgRole.SCIENTIST, invited_by="test"
    )
    squatter = bearer(idp, "idp|squatter", "victim@acme.test", email_verified=False)
    assert client.get("/api/v1/organizations", headers=squatter).json() == []

    invites = client.get(f"/api/v1/organizations/{ORG}/members", headers=acme).json()[
        "invites"
    ]
    assert [i["email"] for i in invites] == ["victim@acme.test"]


def test_a_disabled_account_is_refused(client, idp, acme) -> None:
    user_id = member_id(client, acme, ADMIN[1])
    auth_store.set_active(user_id, False)
    response = client.get("/api/v1/organizations", headers=acme)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_disabled"


# --------------------------------------------------------------------------- #
# Member management
# --------------------------------------------------------------------------- #
def test_admin_invites_a_scientist_who_joins_on_first_sign_in(
    client, idp, acme
) -> None:
    added = client.post(
        f"/api/v1/organizations/{ORG}/members",
        headers=acme,
        json={"email": "Sci@Acme.test", "role": "scientist"},
    )
    assert added.status_code == 201
    assert added.json()["invite"]["email"] == "sci@acme.test"

    sci = bearer(idp, "idp|sci", "sci@acme.test")
    assert [
        o["id"] for o in client.get("/api/v1/organizations", headers=sci).json()
    ] == [ORG]

    members = client.get(f"/api/v1/organizations/{ORG}/members", headers=sci).json()
    assert {m["email"]: m["role"] for m in members["members"]} == {
        ADMIN[1]: "admin",
        "sci@acme.test": "scientist",
    }
    assert members["invites"] == []


def test_only_admins_manage_members(client, idp, acme) -> None:
    sci = join(client, idp, "idp|sci", "sci@acme.test", "scientist")
    target = member_id(client, acme, ADMIN[1])
    base = f"/api/v1/organizations/{ORG}/members"

    assert (
        client.post(
            base, headers=sci, json={"email": "x@acme.test", "role": "admin"}
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"{base}/{target}", headers=sci, json={"role": "scientist"}
        ).status_code
        == 403
    )
    assert client.delete(f"{base}/{target}", headers=sci).status_code == 403
    assert (
        client.get(base, headers=sci).status_code == 200
    )  # members can see the roster


def test_non_members_cannot_see_or_change_another_orgs_roster(
    client, idp, acme
) -> None:
    outsider = bearer(idp, "idp|out", "out@elsewhere.test")
    base = f"/api/v1/organizations/{ORG}/members"
    assert client.get(base, headers=outsider).status_code == 403
    assert (
        client.post(
            base, headers=outsider, json={"email": "o@x.test", "role": "admin"}
        ).status_code
        == 403
    )


def test_the_last_admin_cannot_leave_or_be_demoted(client, idp, acme) -> None:
    me = member_id(client, acme, ADMIN[1])
    base = f"/api/v1/organizations/{ORG}/members/{me}"

    demote = client.patch(base, headers=acme, json={"role": "scientist"})
    assert (demote.status_code, demote.json()["error"]["code"]) == (409, "last_admin")
    assert client.delete(base, headers=acme).status_code == 409

    second = join(client, idp, "idp|two", "two@acme.test", "admin")
    assert (
        client.patch(base, headers=acme, json={"role": "scientist"}).status_code == 200
    )
    # Now `two` is the only admin and the demoted user can no longer manage members.
    assert (
        client.delete(
            f"/api/v1/organizations/{ORG}/members/{me}", headers=acme
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/api/v1/organizations/{ORG}/members/{me}", headers=second
        ).status_code
        == 204
    )


def test_invites_can_be_revoked_and_roles_changed(client, idp, acme) -> None:
    base = f"/api/v1/organizations/{ORG}"
    invite = client.post(
        f"{base}/members",
        headers=acme,
        json={"email": "later@acme.test", "role": "technician"},
    ).json()["invite"]
    assert (
        client.delete(f"{base}/member-invites/{invite['id']}", headers=acme).status_code
        == 204
    )
    assert (
        client.delete(f"{base}/member-invites/{invite['id']}", headers=acme).status_code
        == 404
    )
    assert client.get(f"{base}/members", headers=acme).json()["invites"] == []

    join(client, idp, "idp|t", "t@acme.test", "technician")
    uid = member_id(client, acme, "t@acme.test")
    changed = client.patch(
        f"{base}/members/{uid}", headers=acme, json={"role": "qa_reviewer"}
    )
    assert changed.json()["role"] == "qa_reviewer"


def test_membership_changes_are_audited_without_personal_data(
    client, idp, acme
) -> None:
    client.post(
        f"/api/v1/organizations/{ORG}/members",
        headers=acme,
        json={"email": "pii@acme.test", "role": "scientist"},
    )
    events = client.get(
        f"/api/v1/audit/events?organization_id={ORG}", headers=acme
    ).json()
    types = [event["event_type"] for event in events]
    assert "auth.organization_created" in types
    assert "auth.member_invited" in types
    assert "@" not in json.dumps(events)


def test_removed_members_lose_access_immediately(client, idp, acme) -> None:
    sci = join(client, idp, "idp|sci", "sci@acme.test", "scientist")
    uid = member_id(client, acme, "sci@acme.test")
    assert (
        client.delete(
            f"/api/v1/organizations/{ORG}/members/{uid}", headers=acme
        ).status_code
        == 204
    )
    assert client.get("/api/v1/organizations", headers=sci).json() == []
    assert (
        client.get(f"/api/v1/organizations/{ORG}/members", headers=sci).status_code
        == 403
    )


# --------------------------------------------------------------------------- #
# Roles inside the ELN
# --------------------------------------------------------------------------- #
def _legacy_experiment(client, headers) -> dict:
    response = client.post(
        "/api/v1/experiments",
        headers=headers,
        json={"organization_id": ORG, "name": "Assay", "blocks": []},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _set_status(client, headers, experiment_id: str, status: str):
    version = client.get(
        f"/api/v1/experiments/{experiment_id}/versions", headers=headers
    ).json()[0]
    return client.patch(
        f"/api/v1/experiments/{experiment_id}/versions/{version['id']}",
        headers=headers,
        json={"status": status},
    )


def test_qa_reviewer_reads_and_signs_but_cannot_edit(client, idp, acme) -> None:
    qa = join(client, idp, "idp|qa", "qa@acme.test", "qa_reviewer")
    experiment = _legacy_experiment(client, acme)

    assert (
        client.get(f"/api/v1/experiments/{experiment['id']}", headers=qa).status_code
        == 200
    )
    forbidden = [
        client.post(
            "/api/v1/experiments",
            headers=qa,
            json={"organization_id": ORG, "name": "x", "blocks": []},
        ),
        client.post(
            "/api/v1/workspaces",
            headers=qa,
            json={"organization_id": ORG, "name": "W", "category": "custom"},
        ),
        _set_status(client, qa, experiment["id"], "in_review"),
    ]
    assert [r.status_code for r in forbidden] == [403, 403, 403]

    assert _set_status(client, acme, experiment["id"], "in_review").status_code == 200
    assert _set_status(client, qa, experiment["id"], "signed").status_code == 200


def test_technician_edits_but_cannot_sign(client, idp, acme) -> None:
    tech = join(client, idp, "idp|tech", "tech@acme.test", "technician")
    experiment = _legacy_experiment(client, tech)
    assert _set_status(client, tech, experiment["id"], "in_review").status_code == 200

    refused = _set_status(client, tech, experiment["id"], "signed")
    assert refused.status_code == 403
    assert (
        refused.json()["error"]["details"]["required_permission"] == "experiments:sign"
    )


def test_scientist_can_sign(client, idp, acme) -> None:
    sci = join(client, idp, "idp|sci", "sci@acme.test", "scientist")
    experiment = _legacy_experiment(client, sci)
    assert _set_status(client, sci, experiment["id"], "in_review").status_code == 200
    assert _set_status(client, sci, experiment["id"], "signed").status_code == 200


def test_technician_cannot_manage_a_workspace_but_can_work_in_it(
    client, idp, acme
) -> None:
    tech = join(client, idp, "idp|tech", "tech@acme.test", "technician")
    workspace = client.post(
        "/api/v1/workspaces",
        headers=acme,
        json={"organization_id": ORG, "name": "Cloning", "category": "custom"},
    ).json()

    project = client.post(
        "/api/v1/projects",
        headers=tech,
        json={"organization_id": ORG, "workspace_id": workspace["id"], "name": "P"},
    )
    assert project.status_code == 201, project.text

    wid = workspace["id"]
    assert client.delete(f"/api/v1/workspaces/{wid}", headers=tech).status_code == 403
    share = client.post(
        f"/api/v1/workspaces/{wid}/shares",
        headers=tech,
        json={"subject": "x@y.test", "role": "viewer"},
    )
    assert share.status_code == 403


def test_external_collaborator_sees_only_what_is_shared_by_verified_email(
    client, idp, acme
) -> None:
    ext = join(client, idp, "idp|ext", "Ext@Partner.test", "external_collaborator")
    workspace = client.post(
        "/api/v1/workspaces",
        headers=acme,
        json={"organization_id": ORG, "name": "Shared", "category": "custom"},
    ).json()
    client.post(
        "/api/v1/workspaces",
        headers=acme,
        json={"organization_id": ORG, "name": "Private", "category": "custom"},
    )

    assert client.get("/api/v1/organizations", headers=ext).json() == []
    assert (
        client.get(f"/api/v1/workspaces?organization_id={ORG}", headers=ext).status_code
        == 403
    )
    assert client.get("/api/v1/workspaces", headers=ext).json() == []

    shared = client.post(
        f"/api/v1/workspaces/{workspace['id']}/shares",
        headers=acme,
        json={"subject": "EXT@partner.test", "role": "viewer"},
    )
    assert shared.status_code == 201
    assert shared.json()["subject"] == "ext@partner.test"

    visible = client.get("/api/v1/workspaces", headers=ext).json()
    assert [w["name"] for w in visible] == ["Shared"]

    write = client.post(
        "/api/v1/projects",
        headers=ext,
        json={"organization_id": ORG, "workspace_id": workspace["id"], "name": "nope"},
    )
    assert write.status_code == 403


def test_an_unverified_email_does_not_inherit_email_shares(client, idp, acme) -> None:
    workspace = client.post(
        "/api/v1/workspaces",
        headers=acme,
        json={"organization_id": ORG, "name": "Shared", "category": "custom"},
    ).json()
    client.post(
        f"/api/v1/workspaces/{workspace['id']}/shares",
        headers=acme,
        json={"subject": "target@partner.test", "role": "viewer"},
    )
    impostor = bearer(idp, "idp|imp", "target@partner.test", email_verified=False)
    assert client.get("/api/v1/workspaces", headers=impostor).json() == []

    real = bearer(idp, "idp|real", "target@partner.test", email_verified=True)
    assert [
        w["name"] for w in client.get("/api/v1/workspaces", headers=real).json()
    ] == ["Shared"]
