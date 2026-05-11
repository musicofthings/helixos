# Schema Guide

Schemas are the canonical source for cross-language contracts.

## Rules

- Use JSON Schema Draft 2020-12.
- Include `$id`, `title`, `type`, and `required`.
- Use explicit enums for controlled scientific vocabularies.
- Add compatible fields; avoid renaming or changing semantics.
- Every schema must have at least one example in `examples/`.

## Naming

```txt
schemas/<domain>/<entity>.schema.json
```

Example:

```txt
schemas/eln/experiment.schema.json
```

## Required Common Fields

- `id`
- `organization_id`
- `created_at`
- `updated_at`
