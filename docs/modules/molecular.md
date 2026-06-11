# Molecular Biology Workspace

The molecular module owns sequences, plasmids, annotations, restriction analysis, ORF detection, GC analysis, and visualization data.

**Related:** [auth.md](auth.md) · [mcp.md](mcp.md) · [API_CONTRACTS.md](../../API_CONTRACTS.md)

## Supported Formats (planned)

- FASTA
- GenBank
- SnapGene
- SBOL
- CSV

## User Surface

The workspace **Sequences** tab provides a client-side analyzer (length, GC, ORF scan). Demo sequence metadata is served by the API.

The **Connectors** tab can send the current sequence to BioPython Local ([mcp.md](mcp.md)) for server-side stats via the desktop MCP bridge.

## API Surface

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/api/v1/sequences/{sequence_id}` | Sequence metadata visible to the authenticated actor |

Example response: [API_CONTRACTS.md](../../API_CONTRACTS.md#example-sequence-response).

## Design Notes

Keep parsing, analysis, and visualization projection separate so jobs can run asynchronously and UI rendering stays fast. Long-running analysis should dispatch through [MCP](mcp.md) or a future molecular job queue.

## Audit And Permissions

Sequence records are tenant-scoped by `organization_id`. Retrieval checks [auth](auth.md) actor visibility before returning metadata.

Future: `molecular.analysis_started` audit events for regulated pipelines.
