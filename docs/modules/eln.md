# Electronic Lab Notebook

The ELN module owns experiment records, protocol templates, structured blocks, version history, signatures, and audit trail.

## Block Types

- Text
- Table
- Protocol steps
- Reagent list
- Sequence
- Image
- Chart
- AI annotation

## Compliance Notes

Signed experiment records are immutable. Corrections should be additive and auditable.

## API Surface

- `POST /api/v1/experiments` creates a draft only when the actor can access the submitted `organization_id`.
- `GET /api/v1/experiments` lists records scoped to the authenticated actor's organizations.

## Audit And Permissions

Experiment creation and listing are tenant-scoped through the auth actor. The in-memory starter service records activity only for local development; durable audit events should be introduced with the database layer before regulated use.
