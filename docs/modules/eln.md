# Electronic Lab Notebook

The ELN module is the core of HelixOS — the durable, tenant-scoped, audited system of record intended to replace Benchling and similar tools. It owns the full lab hierarchy: workspaces, projects, versioned experiments, samples, and datasets.

**Related:** [auth.md](auth.md) · [molecular.md](molecular.md) · [ai.md](ai.md) · [audit.md](audit.md) · [API_CONTRACTS.md](../../API_CONTRACTS.md)

## Data Hierarchy

```txt
Workspace (category)          molecular biology, biochemistry, microbiology, ... (user-defined)
  └─ Project                  user-defined program of work
       └─ Experiment          a "repo" that tracks a HEAD version
            ├─ ExperimentVersion   immutable snapshot ("commit"), git-style lineage
            └─ Sample          up to 96 per experiment, optional 96-well plate position
                 └─ Dataset    DNA / RNA / protein sequence, measurement, or file
```

Every entity carries `organization_id` and is isolated by tenant. Defaults: each organization can be seeded with **Molecular Biology**, **Biochemistry**, and **Microbiology** workspaces via `POST /api/v1/workspaces/seed-defaults`.

## Experiment Versioning ("git for experiments")

- An **Experiment** is a container with a `head_version_id` and `version_count`.
- Each edit is committed as an immutable **ExperimentVersion** with a `version_number`, a `parent_version_id` (supporting linear history and branches), a commit `message`, `blocks`, and an `author_subject`.
- Committing a version advances HEAD. History is retrievable in full.
- Version lifecycle status: `draft` ↔ `in_review` → `signed`. **Signed versions are immutable** — corrections are made by committing a new version, keeping the record additive and auditable.

## Samples & Plates

- An experiment holds at most **96 samples** (a standard 96-well plate).
- `well_position` is optional; when set it must be a valid coordinate on an 8×12 plate (`A1`–`H12`), normalized to upper-case, and unique within the experiment.
- `sample_type`: `dna`, `rna`, `protein`, `cell`, `tissue`, `reagent`, `other`.

## Datasets

Datasets attach measured or sequence data to a sample. `dataset_type`: `dna_sequence`, `rna_sequence`, `protein_sequence`, `measurement`, `file`, `other`. A dataset may reference a [molecular](molecular.md) `Sequence` via `sequence_id`.

## Block Types

Text · Table · Protocol steps · Reagent list · Sequence · Image · Chart · AI annotation.

## User Surface

The web workspace **Experiments** tab calls this module via `packages/api-client`:

- Create experiment → `POST /api/v1/experiments` (creates version 1)
- List experiments → `GET /api/v1/experiments`
- Load version history / HEAD content → `GET /api/v1/experiments/{id}/versions`
- Send for review / sign → `PATCH /api/v1/experiments/{id}/versions/{version_id}`

The **Agent panel** can include `experiment_id` and `experiment_title` in run context ([ai.md](ai.md)).

## API Surface

See [API_CONTRACTS.md](../../API_CONTRACTS.md) for the full endpoint table (workspaces, projects, experiments, versions, samples, datasets) with request/response examples.

## Persistence

The ELN persists through SQLAlchemy (Postgres in production, SQLite for local/dev) when `HELIX_DATABASE_URL` is set; otherwise an in-memory store is used for tests and quick local runs. See [db](../../services/api/helixos/db/) and the audit module for the same store pattern.

## Audit And Permissions

All mutations are tenant-scoped through the [auth](auth.md) actor and recorded in [audit](audit.md):
`eln.workspace_created`, `eln.workspaces_seeded`, `eln.project_created`, `eln.project_updated`,
`eln.experiment_created`, `eln.experiment_version_committed`, `eln.experiment_version_status_changed`,
`eln.sample_created`, `eln.sample_updated`, `eln.dataset_created`. Agent runs that reference experiments emit `ai.*` audit events.
