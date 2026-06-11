# AI Copilot Layer

The AI module provides agent sessions and streaming runs for lab copilots. Runs emit [audit events](audit.md) for session creation, tool calls, and completion.

**Related:** [auth.md](auth.md) · [eln.md](eln.md) · [audit.md](audit.md) · [prompts/eln_copilot.md](../../prompts/eln_copilot.md) · [desktop.md](desktop.md)

## User Surface

The workspace **Agent panel** (`apps/web/components/agent/agent-panel.tsx`):

1. Creates a session via `POST /api/v1/ai/sessions`
2. Streams a run via `POST /api/v1/ai/runs` (SSE)
3. Passes ELN/sequence context from the active workspace state

Events appear in the sidebar audit trail when [audit storage](audit.md) is configured.

## Current Behavior

- Sessions are scoped to an authenticated organization ([auth](auth.md)).
- Runs stream Server-Sent Events: `token`, `tool_call`, `done`, `error`.
- Stub provider reads [prompts/eln_copilot.md](../../prompts/eln_copilot.md).
- Regulated steps record audit events: `ai.session_created`, `ai.run_started`, `ai.tool_call`, `ai.run_completed`, `ai.run_failed`.

## Provider Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `HELIX_AI_PROVIDER` | `stub` | `stub`, `openai`, or `vertex` |
| `HELIX_OPENAI_API_KEY` | unset | API key for OpenAI-compatible providers |
| `HELIX_OPENAI_BASE_URL` | `https://api.openai.com/v1` | Compatible API base (Ollama, OpenRouter, etc.) |
| `HELIX_OPENAI_MODEL` | `gpt-4o-mini` | Model name |
| `GOOGLE_CLOUD_PROJECT` | unset | Vertex project ID |
| `GOOGLE_CLOUD_LOCATION` | `us-west1` | Vertex region |
| `HELIX_VERTEX_MODEL` | `gemini-2.0-flash-001` | Vertex Gemini model |

If `HELIX_AI_PROVIDER=openai` is set without an API key, HelixOS falls back to the stub provider. Same for `vertex` without a project ID.

Vertex install:

```bash
pip install -e 'services/api[vertex]'
export GOOGLE_GENAI_USE_VERTEXAI=1
export HELIX_AI_PROVIDER=vertex
export GOOGLE_CLOUD_PROJECT=your-project
```

Set provider env vars on the API process (browser `:8000` or desktop sidecar `:8765`).

## API Surface

| Method | Path | Behavior |
| --- | --- | --- |
| `POST` | `/api/v1/ai/sessions` | Create agent session |
| `POST` | `/api/v1/ai/runs` | Start run; returns `text/event-stream` |

Examples: [API_CONTRACTS.md](../../API_CONTRACTS.md).

## Audit And Permissions

Agent runs require bearer authentication and [organization access](auth.md). Trace and tool-call events are persisted by [audit.md](audit.md) when `HELIX_DATABASE_URL` is set (SQLite in desktop dev, Postgres in server deploys).

Verify chain integrity: `GET /api/v1/audit/verify?organization_id=org_demo`.

## Example SSE Events

```txt
event: tool_call
data: {"tool": "list_experiments", "status": "completed", "count": 2}

event: token
data: {"content": "Suggested ", "run_id": "run_abc123"}

event: done
data: {"run_id": "run_abc123", "status": "completed"}
```
