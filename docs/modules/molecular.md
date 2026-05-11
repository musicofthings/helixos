# Molecular Biology Workspace

The molecular module owns sequences, plasmids, annotations, restriction analysis, ORF detection, GC analysis, and visualization data.

## Supported Formats

- FASTA
- GenBank
- SnapGene
- SBOL
- CSV

## Agent Notes

Keep parsing, analysis, and visualization projection separate so jobs can run asynchronously and UI rendering stays fast.

## API Surface

- `GET /api/v1/sequences/{sequence_id}` fetches sequence metadata visible to the authenticated actor.

## Audit And Permissions

Sequence records are tenant-scoped by `organization_id`. Retrieval checks actor visibility before returning metadata. Future analysis jobs should emit explicit audit events and run asynchronously when they perform long-running computation.
