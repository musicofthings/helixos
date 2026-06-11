export type ExperimentStatus = "draft" | "in_review" | "signed" | "amended" | "archived";

export type ExperimentBlockType =
  | "text"
  | "table"
  | "protocol_steps"
  | "reagent_list"
  | "sequence"
  | "image"
  | "chart"
  | "ai_annotation";

export interface ExperimentBlock {
  type: ExperimentBlockType;
  content: unknown;
}

export interface Experiment {
  id: string;
  organization_id: string;
  project_id?: string;
  title: string;
  status: ExperimentStatus;
  blocks: ExperimentBlock[];
  created_at: string;
  updated_at: string;
}

export interface ExperimentCreate {
  organization_id: string;
  title: string;
  project_id?: string;
  blocks: ExperimentBlock[];
}

export interface ExperimentStatusUpdate {
  status: ExperimentStatus;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
}

export type MoleculeType = "dna" | "rna" | "protein";

export type Topology = "linear" | "circular";

export interface SequenceFeature {
  name: string;
  start: number;
  end: number;
  kind: string;
}

export interface Sequence {
  id: string;
  organization_id: string;
  name: string;
  molecule_type: MoleculeType;
  topology: Topology;
  length: number;
  features: SequenceFeature[];
  created_at: string;
  updated_at: string;
}

export interface ConnectorManifest {
  id: string;
  name: string;
  description: string;
  scopes: string[];
  transport: string;
  enabled_by_default: boolean;
}

export interface ConnectorJobRequest {
  connector_id: string;
  tool: string;
  arguments?: Record<string, unknown>;
}

export interface ConnectorJobResult {
  connector_id: string;
  tool: string;
  status: string;
  result?: unknown;
}

export interface AuditEvent {
  id: string;
  organization_id: string;
  actor_subject: string;
  event_type: string;
  resource_type?: string;
  resource_id?: string;
  payload: Record<string, unknown>;
  created_at: string;
  previous_hash?: string | null;
  event_hash?: string | null;
  sequence_number?: number | null;
}

export interface AuditChainVerification {
  organization_id: string;
  valid: boolean;
  event_count: number;
  head_hash?: string | null;
  message: string;
}

export type AgentRunStatus = "queued" | "running" | "completed" | "failed";

export interface AgentSession {
  id: string;
  organization_id: string;
  created_at: string;
  updated_at: string;
}

export interface AgentRunContext {
  experiment_id?: string;
  experiment_title?: string;
  sequence_length?: number;
}

export interface AgentRunCreate {
  session_id: string;
  message: string;
  context?: AgentRunContext;
}

export type AgentStreamEventType = "token" | "tool_call" | "done" | "error";

export interface AgentStreamEvent {
  event: AgentStreamEventType;
  data: Record<string, unknown>;
}
