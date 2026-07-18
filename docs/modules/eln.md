# Electronic Lab Notebook

The ELN module is the core of HelixOS — the durable, tenant-scoped, audited system of record intended to replace Benchling and similar tools. It owns the full lab hierarchy: workspaces, projects, versioned experiments, samples, and datasets.

**Related:** [auth.md](auth.md) · [molecular.md](molecular.md) · [ai.md](ai.md) · [audit.md](audit.md) · [API_CONTRACTS.md](../../API_CONTRACTS.md)

## Data Hierarchy

```txt
Workspace (category + optional subcategory)   user-defined; category chosen at creation
  ├─ Protocol                 reusable procedure library (manual or imported stub)
  └─ Project                  user-defined program of work
       └─ Experiment          a "repo" that tracks a HEAD version — created *inside* a project
            ├─ ExperimentVersion   immutable snapshot ("commit"), git-style lineage
            └─ Sample          up to 96 per experiment, optional 96-well plate position
                 └─ Dataset    DNA / RNA / protein sequence, measurement, or file
```

Every entity carries `organization_id` and is isolated by tenant. Defaults: each organization can be seeded with **Molecular Biology**, **Biochemistry**, and **Microbiology** workspaces via `POST /api/v1/workspaces/seed-defaults`.

### Workspace categories & subcategories

A workspace is created by choosing a `category`; some categories carry an optional free-string `subcategory`:

| Category | Suggested subcategories |
| --- | --- |
| `molecular_biology` | — |
| `biochemistry` | — |
| `microbiology` | — |
| `next_gen_sequencing` | DNA, RNA, Protein |
| `digital_pathology` | Cells, Tissues |
| `programmable_bio` | Single-cell experiments, PerturbGen, Protein-protein interaction studies (extensible) |

The suggested subcategory lists live in `CATEGORY_SUBCATEGORIES` (`eln/schemas.py`) and are mirrored in the web create-workspace form. They are advisory: `subcategory` is stored as a free string, and the form's "Other…" option lets labs add their own (e.g. new Programmable Bio assays) without a schema change. `genomics` and `cell_biology` are retained only so workspaces saved under the earlier taxonomy still load.

### Creating, switching, deleting, and sharing workspaces

Workspaces are **sidebar channels** (Slack-style). Switching happens on the main left rail; create/select opens that workspace’s home surface.

- **Create** — `+` in the Workspaces sidebar section (category → subcategory form). Success selects the new workspace and opens its home.
- **Switch** — click a workspace channel in the main sidebar.
- **Delete** — from workspace home; confirmation dialog; cascades the full subtree (and cleans up shares/invites). Owner/org members only.
- **Share** — from workspace home: collaborator grants (`viewer` \| `editor`) and invite links. Invite accept URLs are shown once at create time; list responses redact tokens. Accepting an invite creates a grant and surfaces the workspace in the actor's list even without org membership (shared-with-me).

**Access model:** org members are workspace owners. Share-only **viewers** can read the subtree; **editors** can mutate under the workspace but cannot delete the workspace or manage shares.

**Experiments are always created nested under a project** in the UI. `DELETE` on a workspace, project, or experiment cascades to everything beneath it in one transaction (the web UI requires an explicit confirmation).
## Experiment Versioning ("git for experiments")

- An **Experiment** is a container with a `head_version_id` and `version_count`.
- Each edit is committed as an immutable **ExperimentVersion** with a `version_number`, a `parent_version_id` (supporting linear history and branches), a commit `message`, `blocks`, and an `author_subject`.
- Committing a version advances HEAD. History is retrievable in full.
- Version lifecycle status: `draft` ↔ `in_review` → `signed`. **Signed versions are immutable** — corrections are made by committing a new version, keeping the record additive and auditable.

## Samples & Plates

- An experiment holds at most **96 samples** (a standard 96-well plate).
- `well_position` is optional; when set it must be a valid coordinate on an 8×12 plate (`A1`–`H12`), normalized to upper-case, and unique within the experiment.
- `sample_type`: `dna`, `rna`, `protein`, `cell`, `tissue`, `reagent`, `other`.
- `sample_status`: `planned`, `active`, `consumed`, `archived`.
- Samples can be updated (`PATCH`) including moving wells, and deleted (`DELETE`) with cascade to attached datasets.
- Plate UX: empty well → add form; with a sample selected, empty well offers **Move here** or **Add new**.

## Datasets

Datasets attach measured or sequence data to a sample. `dataset_type`: `dna_sequence`, `rna_sequence`, `protein_sequence`, `measurement`, `file`, `other`. A dataset may reference a [molecular](molecular.md) `Sequence` via `sequence_id`.

## Block Types

Text · Table · Protocol steps · Reagent list · Sequence · Image · Chart · AI annotation.

## User Surface

Shell layout (Slack-style channels):

- **Main sidebar — Workspaces** — list of workspace channels + create. Selecting a channel opens **workspace home** for that workspace (projects, recent experiments, Share / Delete / Open lab, Agent panel).
- **Main sidebar — Tools** — Lab notebook, Protocols, Sequences, Inventory, Connectors. Lab notebook and Protocols are scoped to the active workspace; Lab shows Project → Experiment only (no nested workspace switcher).
- **Workspace home** — fresh options after create/select; does not host experiment editing.
- **Lab notebook** — ELN workbench: projects/experiments for the active workspace, versioning, 96-well plate, and sample/dataset management.
- **Protocols** — workspace protocol library: create, edit, delete, and import stubs from protocols.io / URL (remote fetch not wired yet).

Lab notebook API usage via `packages/api-client`:

- Create experiment → `POST /api/v1/experiments` (creates version 1)
- List experiments → `GET /api/v1/experiments`
- Load version history / HEAD content → `GET /api/v1/experiments/{id}/versions`
- Send for review / sign → `PATCH /api/v1/experiments/{id}/versions/{version_id}`
- Update / delete samples → `PATCH` / `DELETE /api/v1/samples/{id}`

The **Agent panel** can include `experiment_id` and `experiment_title` in run context ([ai.md](ai.md)).

## API Surface

See [API_CONTRACTS.md](../../API_CONTRACTS.md) for the full endpoint table (workspaces, projects, experiments, versions, samples, datasets) with request/response examples.

## Persistence

The ELN persists through SQLAlchemy (Postgres in production, SQLite for local/dev) when `HELIX_DATABASE_URL` is set; otherwise an in-memory store is used for tests and quick local runs. See [db](../../services/api/helixos/db/) and the audit module for the same store pattern.

## Audit And Permissions

All mutations are tenant-scoped through the [auth](auth.md) actor and recorded in [audit](audit.md):
`eln.workspace_created`, `eln.workspace_deleted`, `eln.workspaces_seeded`,
`eln.workspace_share_granted`, `eln.workspace_share_updated`, `eln.workspace_share_revoked`,
`eln.workspace_invite_created`, `eln.workspace_invite_revoked`, `eln.workspace_invite_accepted`,
`eln.protocol_created`, `eln.protocol_updated`, `eln.protocol_deleted`, `eln.protocol_imported`,
`eln.project_created`, `eln.project_updated`, `eln.project_deleted`, `eln.experiment_created`,
`eln.experiment_deleted`, `eln.experiment_version_committed`, `eln.experiment_version_status_changed`,
`eln.sample_created`, `eln.sample_updated`, `eln.sample_deleted`, `eln.dataset_created`. Agent runs that reference experiments emit `ai.*` audit events.