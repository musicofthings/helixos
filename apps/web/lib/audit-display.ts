import type { AuditEvent } from "@helixos/types";

import { formatExperimentTimestamp } from "./experiment-display";

const EVENT_LABELS: Record<string, string> = {
  "eln.experiment_created": "Experiment created",
  "eln.experiment_status_changed": "Experiment status changed",
  "ai.session_created": "Agent session created",
  "ai.run_started": "Agent run started",
  "ai.tool_call": "Agent tool call",
  "ai.run_completed": "Agent run completed",
  "ai.run_failed": "Agent run failed",
  "mcp.job_started": "Connector job started",
  "mcp.job_completed": "Connector job completed",
  "mcp.job_failed": "Connector job failed"
};

export function formatAuditEventMessage(event: AuditEvent): string {
  const label = EVENT_LABELS[event.event_type] ?? event.event_type;
  const time = formatExperimentTimestamp(event.created_at);
  const resource = event.resource_id ? ` · ${event.resource_id}` : "";
  return `${time} · ${label}${resource}`;
}
