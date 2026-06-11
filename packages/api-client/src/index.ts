import type {
  AgentRunContext,
  AgentSession,
  AgentStreamEvent,
  AuditChainVerification,
  AuditEvent,
  ConnectorJobRequest,
  ConnectorJobResult,
  ConnectorManifest,
  Experiment,
  ExperimentCreate,
  ExperimentStatus,
  ExperimentStatusUpdate,
  Organization,
  Sequence
} from "@helixos/types";

import { HelixOSApiError } from "./errors";

export { HelixOSApiError };

export type HelixOSClientOptions = {
  baseUrl: string;
  token: string;
};

type ApiErrorBody = {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown>;
  };
};

export class HelixOSClient {
  private readonly baseUrl: string;
  private readonly token: string;

  constructor(options: HelixOSClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.token = options.token;
  }

  private headers(extra?: HeadersInit): HeadersInit {
    return {
      Authorization: `Bearer ${this.token}`,
      "Content-Type": "application/json",
      ...extra
    };
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: this.headers(init?.headers)
    });

    if (!response.ok) {
      let body: ApiErrorBody = {};
      try {
        body = (await response.json()) as ApiErrorBody;
      } catch {
        body = {};
      }
      throw new HelixOSApiError(
        response.status,
        body.error?.code ?? "http_error",
        body.error?.message ?? `Request failed with status ${response.status}`,
        body.error?.details ?? {}
      );
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return (await response.json()) as T;
  }

  health(): Promise<{ status: string }> {
    return this.request("/health");
  }

  listOrganizations(): Promise<Organization[]> {
    return this.request("/api/v1/organizations");
  }

  listExperiments(): Promise<Experiment[]> {
    return this.request("/api/v1/experiments");
  }

  createExperiment(payload: ExperimentCreate): Promise<Experiment> {
    return this.request("/api/v1/experiments", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  }

  updateExperimentStatus(experimentId: string, payload: ExperimentStatusUpdate): Promise<Experiment> {
    return this.request(`/api/v1/experiments/${encodeURIComponent(experimentId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    });
  }

  getSequence(sequenceId: string): Promise<Sequence> {
    return this.request(`/api/v1/sequences/${encodeURIComponent(sequenceId)}`);
  }

  listConnectors(): Promise<ConnectorManifest[]> {
    return this.request("/api/v1/mcp/connectors");
  }

  runConnectorJob(payload: ConnectorJobRequest): Promise<ConnectorJobResult> {
    return this.request("/api/v1/mcp/jobs", {
      method: "POST",
      body: JSON.stringify({
        connector_id: payload.connector_id,
        tool: payload.tool,
        arguments: payload.arguments ?? {}
      })
    });
  }

  listAuditEvents(organizationId?: string): Promise<AuditEvent[]> {
    const query = organizationId ? `?organization_id=${encodeURIComponent(organizationId)}` : "";
    return this.request(`/api/v1/audit/events${query}`);
  }

  verifyAuditChain(organizationId: string): Promise<AuditChainVerification> {
    return this.request(`/api/v1/audit/verify?organization_id=${encodeURIComponent(organizationId)}`);
  }

  createAgentSession(organizationId: string): Promise<AgentSession> {
    return this.request("/api/v1/ai/sessions", {
      method: "POST",
      body: JSON.stringify({ organization_id: organizationId })
    });
  }

  async *streamAgentRun(input: {
    sessionId: string;
    message: string;
    context?: AgentRunContext;
  }): AsyncGenerator<AgentStreamEvent> {
    const response = await fetch(`${this.baseUrl}/api/v1/ai/runs`, {
      method: "POST",
      headers: this.headers({ Accept: "text/event-stream" }),
      body: JSON.stringify({
        session_id: input.sessionId,
        message: input.message,
        context: input.context ?? {}
      })
    });

    if (!response.ok) {
      let body: ApiErrorBody = {};
      try {
        body = (await response.json()) as ApiErrorBody;
      } catch {
        body = {};
      }
      throw new HelixOSApiError(
        response.status,
        body.error?.code ?? "http_error",
        body.error?.message ?? `Agent run failed with status ${response.status}`,
        body.error?.details ?? {}
      );
    }

    if (!response.body) {
      throw new HelixOSApiError(500, "stream_error", "Agent run returned an empty stream");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() ?? "";

      for (const chunk of chunks) {
        const event = parseSseChunk(chunk);
        if (event) {
          yield event;
        }
      }
    }

    if (buffer.trim()) {
      const event = parseSseChunk(buffer);
      if (event) {
        yield event;
      }
    }
  }
}

function parseSseChunk(chunk: string): AgentStreamEvent | null {
  const lines = chunk.split("\n");
  let eventType = "message";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      eventType = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  if (!dataLines.length) {
    return null;
  }

  try {
    const data = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
    return { event: eventType as AgentStreamEvent["event"], data };
  } catch {
    return null;
  }
}
