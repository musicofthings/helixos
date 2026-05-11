# System Architecture

HelixOS is a modular monorepo for AI-native laboratory software.

## Runtime Components

- `apps/web`: Next.js TypeScript application for lab users.
- `services/api`: FastAPI service exposing versioned REST APIs.
- `schemas`: Canonical JSON Schemas shared by frontend, backend, and agents.
- `mcp`: Scientific MCP connector manifests and registry metadata.
- `agents`: Agent instructions, workflows, and module scaffolding templates.

## Backend Domains

- `auth`: organizations, workspaces, users, roles, permissions.
- `eln`: experiments, protocol templates, blocks, signatures, audit trail.
- `molecular`: sequences, plasmids, annotations, analyses.
- `inventory`: reagents, lots, vendors, stock, expiry alerts.
- `biobank`: samples, aliquots, storage, genealogy, chain of custody.
- `workflows`: SOPs, state machines, approvals, automation triggers.
- `ai`: provider abstraction, copilots, prompt execution, trace storage.
- `mcp`: connector registry, scopes, job dispatch, manifests.

## Data Principles

- Every tenant-scoped record includes `organization_id`.
- Regulated records include immutable audit events.
- Long-running scientific jobs are asynchronous.
- Files are stored in S3-compatible object storage with database metadata.
- Schemas are versioned and backward compatible.

## Agent Principles

Agents should make narrow module changes, preserve contracts, and update tests and docs in the same change set.
