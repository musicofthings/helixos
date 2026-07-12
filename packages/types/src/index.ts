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

export type WorkspaceCategory =
  | "molecular_biology"
  | "biochemistry"
  | "microbiology"
  | "genomics"
  | "cell_biology"
  | "custom";

export interface Workspace {
  id: string;
  organization_id: string;
  name: string;
  category: WorkspaceCategory;
  description?: string | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceCreate {
  organization_id: string;
  name: string;
  category?: WorkspaceCategory;
  description?: string | null;
}

export type ProjectStatus = "active" | "archived";

export interface Project {
  id: string;
  organization_id: string;
  workspace_id: string;
  name: string;
  description?: string | null;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  organization_id: string;
  workspace_id: string;
  name: string;
  description?: string | null;
}

export interface ProjectUpdate {
  name?: string;
  description?: string | null;
  status?: ProjectStatus;
}

export interface Experiment {
  id: string;
  organization_id: string;
  project_id?: string | null;
  name: string;
  description?: string | null;
  head_version_id?: string | null;
  version_count: number;
  created_at: string;
  updated_at: string;
}

export interface ExperimentCreate {
  organization_id: string;
  project_id?: string | null;
  name: string;
  description?: string | null;
  blocks: ExperimentBlock[];
}

export interface ExperimentVersion {
  id: string;
  experiment_id: string;
  organization_id: string;
  version_number: number;
  parent_version_id?: string | null;
  message: string;
  status: ExperimentStatus;
  blocks: ExperimentBlock[];
  author_subject: string;
  created_at: string;
}

export interface ExperimentVersionCreate {
  message: string;
  blocks: ExperimentBlock[];
  parent_version_id?: string | null;
}

export interface ExperimentStatusUpdate {
  status: ExperimentStatus;
}

export type SampleType = "dna" | "rna" | "protein" | "cell" | "tissue" | "reagent" | "other";

export type SampleStatus = "planned" | "active" | "consumed" | "archived";

export interface Sample {
  id: string;
  organization_id: string;
  experiment_id: string;
  name: string;
  sample_type: SampleType;
  well_position?: string | null;
  status: SampleStatus;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SampleCreate {
  organization_id: string;
  experiment_id: string;
  name: string;
  sample_type?: SampleType;
  well_position?: string | null;
  metadata?: Record<string, unknown>;
}

export interface SampleUpdate {
  name?: string;
  sample_type?: SampleType;
  well_position?: string | null;
  status?: SampleStatus;
  metadata?: Record<string, unknown>;
}

export type DatasetType =
  | "dna_sequence"
  | "rna_sequence"
  | "protein_sequence"
  | "measurement"
  | "file"
  | "other";

export interface Dataset {
  id: string;
  organization_id: string;
  sample_id: string;
  name: string;
  dataset_type: DatasetType;
  sequence_id?: string | null;
  content: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface DatasetCreate {
  organization_id: string;
  sample_id: string;
  name: string;
  dataset_type?: DatasetType;
  sequence_id?: string | null;
  content?: Record<string, unknown>;
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
  organization_id: string;
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
