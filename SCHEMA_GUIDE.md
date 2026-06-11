# Schema Guide

Schemas are the canonical source for cross-language contracts shared by the FastAPI backend (`services/api`), TypeScript clients (`packages/types`), and module documentation.

**Related:** [API_CONTRACTS.md](API_CONTRACTS.md) · [docs/README.md](docs/README.md) · [DOMAIN_GLOSSARY.md](DOMAIN_GLOSSARY.md)

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
