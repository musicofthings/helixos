// AUTO-GENERATED from services/api/helixos/eln/schemas.py — do not edit.
// Regenerate: (cd services/api && python scripts/generate_ts_types.py)

export type WorkspaceCategory =
  | "molecular_biology"
  | "biochemistry"
  | "microbiology"
  | "next_gen_sequencing"
  | "digital_pathology"
  | "programmable_bio"
  | "genomics"
  | "cell_biology"
  | "custom";

export type ProjectStatus =
  | "active"
  | "archived";

export type ExperimentStatus =
  | "draft"
  | "in_review"
  | "signed"
  | "amended"
  | "archived";

export type ExperimentBlockType =
  | "text"
  | "table"
  | "protocol_steps"
  | "reagent_list"
  | "sequence"
  | "image"
  | "chart"
  | "ai_annotation";

export type SampleType =
  | "dna"
  | "rna"
  | "protein"
  | "cell"
  | "tissue"
  | "reagent"
  | "other";

export type SampleStatus =
  | "planned"
  | "active"
  | "consumed"
  | "archived";

export type DatasetType =
  | "dna_sequence"
  | "rna_sequence"
  | "protein_sequence"
  | "measurement"
  | "file"
  | "other";

export type WorkspaceShareRole =
  | "viewer"
  | "editor";

export interface ExperimentBlock {
  type: ExperimentBlockType;
  content: unknown;
}

export interface WorkspaceCreate {
  organization_id: string;
  name: string;
  category?: WorkspaceCategory;
  subcategory?: string | null;
  description?: string | null;
}

export interface Workspace {
  organization_id: string;
  name: string;
  category: WorkspaceCategory;
  subcategory: string | null;
  description: string | null;
  id: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceShareCreate {
  subject: string;
  role?: WorkspaceShareRole;
}

export interface WorkspaceShareUpdate {
  role: WorkspaceShareRole;
}

export interface WorkspaceShare {
  id: string;
  workspace_id: string;
  organization_id: string;
  subject: string;
  role: WorkspaceShareRole;
  granted_by: string;
  created_at: string;
}

export interface WorkspaceInviteCreate {
  role?: WorkspaceShareRole;
  expires_in_hours?: number;
  max_uses?: number | null;
}

export interface WorkspaceInvite {
  id: string;
  workspace_id: string;
  organization_id: string;
  token: string | null;
  role: WorkspaceShareRole;
  created_by: string;
  expires_at: string;
  revoked_at: string | null;
  accepted_count: number;
  max_uses: number | null;
  created_at: string;
}

export interface WorkspaceCollaboration {
  shares: WorkspaceShare[];
  invites: WorkspaceInvite[];
}

export interface ProjectCreate {
  organization_id: string;
  workspace_id: string;
  name: string;
  description?: string | null;
}

export interface ProjectUpdate {
  name?: string | null;
  description?: string | null;
  status?: ProjectStatus | null;
}

export interface Project {
  organization_id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  id: string;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
}

export type ProtocolStatus =
  | "draft"
  | "active"
  | "archived";

export type ProtocolSourceProvider =
  | "manual"
  | "protocols_io"
  | "url";

export type ProtocolImportSourceProvider =
  | "protocols_io"
  | "url";

export interface ProtocolStep {
  order: number;
  title: string;
  body: string;
}

export interface ProtocolCreate {
  organization_id: string;
  workspace_id: string;
  name: string;
  description?: string | null;
  steps?: ProtocolStep[];
  source_provider?: ProtocolSourceProvider;
  source_url?: string | null;
  source_external_id?: string | null;
}

export interface ProtocolUpdate {
  name?: string | null;
  description?: string | null;
  status?: ProtocolStatus | null;
  steps?: ProtocolStep[] | null;
}

export interface Protocol {
  organization_id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  steps: ProtocolStep[];
  source_provider: ProtocolSourceProvider;
  source_url: string | null;
  source_external_id: string | null;
  id: string;
  status: ProtocolStatus;
  created_at: string;
  updated_at: string;
}

export interface ProtocolImportRequest {
  organization_id: string;
  workspace_id: string;
  source_provider?: ProtocolImportSourceProvider;
  source_url?: string | null;
  source_external_id?: string | null;
  name?: string | null;
}

export interface ExperimentCreate {
  organization_id: string;
  project_id?: string | null;
  name: string;
  description?: string | null;
  blocks?: ExperimentBlock[];
}

export interface Experiment {
  id: string;
  organization_id: string;
  project_id: string | null;
  name: string;
  description: string | null;
  head_version_id: string | null;
  version_count: number;
  created_at: string;
  updated_at: string;
}

export interface ExperimentVersionCreate {
  message: string;
  blocks?: ExperimentBlock[];
  parent_version_id?: string | null;
}

export interface ExperimentVersion {
  id: string;
  experiment_id: string;
  organization_id: string;
  version_number: number;
  parent_version_id: string | null;
  message: string;
  status: ExperimentStatus;
  blocks: ExperimentBlock[];
  author_subject: string;
  created_at: string;
}

export interface ExperimentStatusUpdate {
  status: ExperimentStatus;
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
  name?: string | null;
  sample_type?: SampleType | null;
  well_position?: string | null;
  status?: SampleStatus | null;
  metadata?: Record<string, unknown> | null;
}

export interface Sample {
  id: string;
  organization_id: string;
  experiment_id: string;
  name: string;
  sample_type: SampleType;
  well_position: string | null;
  status: SampleStatus;
  metadata: Record<string, unknown>;
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

export interface Dataset {
  id: string;
  organization_id: string;
  sample_id: string;
  name: string;
  dataset_type: DatasetType;
  sequence_id: string | null;
  content: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}
