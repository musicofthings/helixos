"""Concurrency guarantees that SQLite's serialized writes cannot demonstrate.

Skipped unless HELIX_TEST_POSTGRES_URL points at a disposable PostgreSQL
database (CI provides one). Each test releases its threads together with a
barrier so the racing transactions genuinely overlap.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, func, inspect, select

from helixos.db import migrations
from helixos.eln.orm import SampleORM
from helixos.eln.schemas import ExperimentStatus, WorkspaceShare, WorkspaceShareRole
from helixos.eln.service import eln_service
from helixos.eln.stores import InviteUnavailableError, StaleStateError

ORG_DEMO = {"Authorization": "Bearer org-demo-token"}
ADMIN = {"Authorization": "Bearer demo-admin-token"}
THREADS = 8


def _race(count, task):
    """Run ``task(i)`` on ``count`` threads released simultaneously."""
    barrier = threading.Barrier(count)

    def run(i):
        barrier.wait(timeout=30)
        try:
            return task(i)
        except Exception as exc:  # noqa: BLE001 - outcomes are asserted by callers
            return exc

    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(run, range(count)))


def test_sample_capacity_is_serialized(postgres_client) -> None:
    from helixos.eln.schemas import MAX_SAMPLES_PER_EXPERIMENT

    experiment = postgres_client.post(
        "/api/v1/experiments",
        headers=ORG_DEMO,
        json={"organization_id": "org_demo", "name": "Plate", "blocks": []},
    ).json()

    def create(i):
        return postgres_client.post(
            "/api/v1/samples",
            headers=ORG_DEMO,
            json={
                "organization_id": "org_demo",
                "experiment_id": experiment["id"],
                "name": f"s{i}",
                "sample_type": "dna",
            },
        ).status_code

    # Leave exactly one free slot, then race for it.
    for i in range(MAX_SAMPLES_PER_EXPERIMENT - 1):
        assert create(f"pre{i}") == 201

    codes = _race(THREADS, create)
    assert sorted(codes) == [201] + [409] * (THREADS - 1), codes

    from helixos.db.session import session_scope

    with session_scope() as session:
        total = session.scalar(
            select(func.count())
            .select_from(SampleORM)
            .where(SampleORM.experiment_id == experiment["id"])
        )
    assert total == MAX_SAMPLES_PER_EXPERIMENT


def test_invite_max_uses_holds_under_concurrent_acceptance(postgres_client) -> None:
    workspace = postgres_client.post(
        "/api/v1/workspaces",
        headers=ADMIN,
        json={"organization_id": "org_qc", "name": "Race", "category": "custom"},
    ).json()
    token = postgres_client.post(
        f"/api/v1/workspaces/{workspace['id']}/invites",
        headers=ADMIN,
        json={"role": "viewer", "expires_in_hours": 24, "max_uses": 1},
    ).json()["token"]
    store = eln_service._store
    invite = store.get_invite_by_token(token)

    def accept(i):
        share = WorkspaceShare(
            workspace_id=invite.workspace_id,
            organization_id=invite.organization_id,
            subject=f"user_race_{i}",
            role=WorkspaceShareRole.VIEWER,
            granted_by=invite.created_by,
        )
        return store.accept_invite(invite, share)

    results = _race(THREADS, accept)
    winners = [r for r in results if not isinstance(r, Exception)]
    losers = [r for r in results if isinstance(r, InviteUnavailableError)]
    assert len(winners) == 1, results
    assert len(losers) == THREADS - 1, results
    assert store.get_invite(invite.id).accepted_count == 1
    assert len(store.list_shares(invite.workspace_id)) == 1


def test_signed_version_cannot_be_overwritten_by_concurrent_rollback(
    postgres_client,
) -> None:
    experiment = postgres_client.post(
        "/api/v1/experiments",
        headers=ORG_DEMO,
        json={"organization_id": "org_demo", "name": "CAS", "blocks": []},
    ).json()
    store = eln_service._store
    version = store.list_versions(experiment["id"])[0]
    in_review = version.model_copy(update={"status": ExperimentStatus.IN_REVIEW})
    store.update_version(in_review, expected_status=ExperimentStatus.DRAFT)

    def transition(i):
        target = ExperimentStatus.SIGNED if i % 2 == 0 else ExperimentStatus.DRAFT
        return store.update_version(
            in_review.model_copy(update={"status": target}),
            expected_status=ExperimentStatus.IN_REVIEW,
        )

    results = _race(2, transition)
    assert sum(isinstance(r, StaleStateError) for r in results) == 1, results
    final = store.get_version(version.id).status
    assert final in (ExperimentStatus.SIGNED, ExperimentStatus.DRAFT)


def test_concurrent_startup_migrations_apply_once(postgres_url) -> None:
    engine = create_engine(postgres_url, future=True)
    try:
        results = _race(4, lambda _i: migrations.upgrade(engine))
        assert not [r for r in results if isinstance(r, Exception)], results
        applied = [v for r in results for v in r]
        assert applied == [name for name, _ in migrations.MIGRATIONS]
        assert migrations.applied_versions(engine) == applied
        assert "audit_events" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
