"""JSON Schemas under ``schemas/`` must describe what the API actually emits.

The Pydantic models are the implementation; the schemas are the documented,
language-neutral contract (see SCHEMA_GUIDE.md). These tests fail on drift:
property names, required sets, enums, nullability, examples, and live responses.
"""

import enum
import json
import types
import typing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel

from helixos.auth.schemas import Organization
from helixos.eln import schemas as eln
from helixos.molecular.schemas import Sequence

REPO = Path(__file__).resolve().parents[3]
SCHEMAS = REPO / "schemas"
EXAMPLES = REPO / "examples"

# schema file (relative to schemas/) -> Pydantic model that serializes it
CONTRACTS: dict[str, type[BaseModel]] = {
    "auth/organization.schema.json": Organization,
    "eln/workspace.schema.json": eln.Workspace,
    "eln/workspace_share.schema.json": eln.WorkspaceShare,
    "eln/workspace_invite.schema.json": eln.WorkspaceInvite,
    "eln/project.schema.json": eln.Project,
    "eln/protocol.schema.json": eln.Protocol,
    "eln/experiment.schema.json": eln.Experiment,
    "eln/experiment_version.schema.json": eln.ExperimentVersion,
    "eln/sample.schema.json": eln.Sample,
    "eln/dataset.schema.json": eln.Dataset,
    "molecular/sequence.schema.json": Sequence,
}


def _load(path: str) -> dict:
    return json.loads((SCHEMAS / path).read_text())


def _unwrap(annotation):
    """Return (inner annotation, is_nullable) for ``X | None``."""
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        nullable = len(args) != len(typing.get_args(annotation))
        return (args[0] if len(args) == 1 else annotation), nullable
    return annotation, False


def _schema_nullable(node: dict) -> bool:
    kind = node.get("type")
    return (isinstance(kind, list) and "null" in kind) or any(
        o.get("type") == "null" for o in node.get("anyOf", [])
    )


def test_every_schema_file_is_covered_by_a_contract() -> None:
    on_disk = {str(p.relative_to(SCHEMAS)) for p in SCHEMAS.rglob("*.schema.json")}
    assert on_disk == set(CONTRACTS), "add new schemas to CONTRACTS (and vice versa)"


@pytest.mark.parametrize("path", sorted(CONTRACTS))
def test_schema_is_valid_draft_2020_12(path) -> None:
    Draft202012Validator.check_schema(_load(path))


@pytest.mark.parametrize("path", sorted(CONTRACTS))
def test_schema_matches_model_shape(path) -> None:
    schema, model = _load(path), CONTRACTS[path]
    fields = model.model_fields

    assert set(schema["properties"]) == set(fields), "property names drifted"
    # Responses serialize every field, so every field is required on the wire.
    assert set(schema["required"]) == set(fields), "required set drifted"

    for name, field in fields.items():
        inner, nullable = _unwrap(field.annotation)
        node = schema["properties"][name]
        assert _schema_nullable(node) == nullable, f"{name}: nullability drifted"
        if isinstance(inner, type) and issubclass(inner, enum.Enum):
            # null is listed in a nullable enum; nullability is asserted above.
            assert set(node["enum"]) - {None} == {m.value for m in inner}, (
                f"{name}: enum drifted"
            )


@pytest.mark.parametrize("path", sorted(CONTRACTS))
def test_every_schema_has_a_valid_example(path) -> None:
    schema, model = _load(path), CONTRACTS[path]
    example_path = EXAMPLES / path.replace(".schema.json", ".json")
    assert example_path.exists(), f"missing example {example_path.relative_to(REPO)}"
    example = json.loads(example_path.read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(example)
    model.model_validate(example)


# --- live responses ----------------------------------------------------------

ORG_DEMO = {"Authorization": "Bearer org-demo-token"}


def _validator(path: str) -> Draft202012Validator:
    return Draft202012Validator(_load(path), format_checker=FormatChecker())


def test_live_api_responses_conform_to_schemas(memory_client: TestClient) -> None:
    client = memory_client

    def ok(response, status=(200, 201)):
        assert response.status_code in status, response.text
        return response.json()

    workspace = ok(
        client.post(
            "/api/v1/workspaces",
            headers=ORG_DEMO,
            json={
                "organization_id": "org_demo",
                "name": "Contract",
                "category": "custom",
            },
        )
    )
    project = ok(
        client.post(
            "/api/v1/projects",
            headers=ORG_DEMO,
            json={
                "organization_id": "org_demo",
                "workspace_id": workspace["id"],
                "name": "P",
            },
        )
    )
    protocol = ok(
        client.post(
            "/api/v1/protocols",
            headers=ORG_DEMO,
            json={
                "organization_id": "org_demo",
                "workspace_id": workspace["id"],
                "name": "Proto",
                "steps": [{"order": 1, "title": "Go"}],
            },
        )
    )
    experiment = ok(
        client.post(
            "/api/v1/experiments",
            headers=ORG_DEMO,
            json={
                "organization_id": "org_demo",
                "project_id": project["id"],
                "name": "Exp",
                "blocks": [{"type": "text", "content": "hi"}],
            },
        )
    )
    versions = ok(
        client.get(f"/api/v1/experiments/{experiment['id']}/versions", headers=ORG_DEMO)
    )
    sample = ok(
        client.post(
            "/api/v1/samples",
            headers=ORG_DEMO,
            json={
                "organization_id": "org_demo",
                "experiment_id": experiment["id"],
                "name": "S",
                "sample_type": "dna",
                "well_position": "A1",
            },
        )
    )
    dataset = ok(
        client.post(
            "/api/v1/datasets",
            headers=ORG_DEMO,
            json={
                "organization_id": "org_demo",
                "sample_id": sample["id"],
                "name": "D",
                "dataset_type": "other",
                "content": {"k": 1},
            },
        )
    )
    share = ok(
        client.post(
            f"/api/v1/workspaces/{workspace['id']}/shares",
            headers=ORG_DEMO,
            json={"subject": "colleague@example.com", "role": "viewer"},
        )
    )
    invite = ok(
        client.post(
            f"/api/v1/workspaces/{workspace['id']}/invites",
            headers=ORG_DEMO,
            json={"role": "viewer", "expires_in_hours": 1},
        )
    )
    organizations = ok(client.get("/api/v1/organizations", headers=ORG_DEMO))

    checks = [
        ("eln/workspace.schema.json", workspace),
        ("eln/project.schema.json", project),
        ("eln/protocol.schema.json", protocol),
        ("eln/experiment.schema.json", experiment),
        ("eln/experiment_version.schema.json", versions[0]),
        ("eln/sample.schema.json", sample),
        ("eln/dataset.schema.json", dataset),
        ("eln/workspace_share.schema.json", share),
        ("eln/workspace_invite.schema.json", invite),
        ("auth/organization.schema.json", organizations[0]),
    ]
    for path, payload in checks:
        errors = list(_validator(path).iter_errors(payload))
        assert not errors, f"{path}: {[e.message for e in errors]}"
