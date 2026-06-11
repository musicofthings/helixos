# Electronic Lab Notebook

The ELN module owns experiment records, protocol templates, structured blocks, version history, signatures, and audit trail integration.

**Related:** [auth.md](auth.md) · [ai.md](ai.md) · [audit.md](audit.md) · [API_CONTRACTS.md](../../API_CONTRACTS.md)

## Block Types

- Text
- Table
- Protocol steps
- Reagent list
- Sequence
- Image
- Chart
- AI annotation

## User Surface

The web workspace **Experiments** tab calls this module via `packages/api-client`:

- Create draft → `POST /api/v1/experiments`
- List records → `GET /api/v1/experiments`

The **Agent panel** can include `experiment_id` and `experiment_title` in run context ([ai.md](ai.md)).

## API Surface

| Method | Path | Behavior |
| --- | --- | --- |
| `POST` | `/api/v1/experiments` | Create draft when actor can access `organization_id` |
| `GET` | `/api/v1/experiments` | List records scoped to actor organizations |
| `PATCH` | `/api/v1/experiments/{experiment_id}` | Update lifecycle status (`draft` → `in_review` → `signed`) |

## Compliance Notes

Signed experiment records should be immutable. Corrections should be additive and auditable. Status transitions use `PATCH /api/v1/experiments/{id}` and emit audit events.

## Audit And Permissions

Experiment creation and status changes are tenant-scoped through the [auth](auth.md) actor and recorded in [audit](audit.md) (`eln.experiment_created`, `eln.experiment_status_changed`). Agent runs that reference experiments emit `ai.*` audit events when the copilot is used from the workspace.
